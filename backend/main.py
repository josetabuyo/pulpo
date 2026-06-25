import asyncio
import logging
import os
import random
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telegram.ext import Application

from pathlib import Path

from config import load_config, get_telegram_connections
from db import init_db, google_connection_exists, create_google_connection
from bots.telegram_bot import build_telegram_app
from state import clients
from api.auth import router as auth_router
from api.auth_bot import router as auth_bot_router, limiter as bot_limiter
from api.bots import router as bots_router
from api.connections import router as connections_router
from api.telegram_api import router as telegram_router
from api.messages import router as messages_router
from api.sim import router as sim_router
from api.client import router as client_router
from api.logs import router as logs_router
from api.bot_portal import router as bot_portal_router
from api.contacts import router as contacts_router
from api.summarizer import router as summarizer_router
from api.flows import router as flows_router, seed_default_flows
from api.fb_session import router as fb_session_router
from api.wavi import router as wavi_router
from api.settings import router as settings_router
from api.architecture import router as architecture_router
import sim as sim_engine
import wavi_poller

# ── Logging con rotación automática ──────────────────────────────────────────
_PROJECT_DIR = Path(__file__).parent.parent
_LOG_PATH = _PROJECT_DIR / "monitor" / "backend.log"


class _FileLogFilter(logging.Filter):
    """Excluye polling de Telegram y ruido de sistema del archivo de log."""
    _EXCLUDE = (
        'getUpdates',
        'No new updates found',
        'Calling Bot API endpoint',
        'Call to Bot API endpoint',
    )

    def filter(self, record):
        msg = record.getMessage()
        if any(p in msg for p in self._EXCLUDE):
            return False
        return True


class _TelegramTimedOutFilter(logging.Filter):
    """Suprime TimedOut de telegram.ext._updater durante el cleanup al apagar — es inocuo."""
    def filter(self, record):
        if record.exc_info and record.exc_info[1] is not None:
            from telegram.error import TimedOut
            if isinstance(record.exc_info[1], TimedOut):
                return False
        return True


class _UvicornPollingFilter(logging.Filter):
    """Excluye del log de acceso de uvicorn los endpoints que la UI consulta periódicamente."""
    _POLLING = (
        '"GET /api/bots HTTP',
        '"GET /api/logs/latest',
        '/paused HTTP',          # /api/bot/{id}/paused
    )

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not any(p in msg for p in self._POLLING)


_log_handler = RotatingFileHandler(
    _LOG_PATH,
    maxBytes=5 * 1024 * 1024,   # 5 MB por archivo
    backupCount=3,               # backend.log + .1 + .2 + .3 → máx ~20 MB
    encoding="utf-8",
)
_log_handler.setLevel(logging.INFO)   # solo INFO+ va al archivo; DEBUG nunca
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
_log_handler.addFilter(_FileLogFilter())

# Sin _stdout_handler: start.sh redirige stdout al log; tener ambos duplicaría entradas
# y permitiría que DEBUG de librerías (telegram, httpx) se cuele al archivo vía stdout capturado.
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[_log_handler],
    force=True,  # garantiza que nuestro handler sea el único en root, ignora handlers previos
)
# Silenciar librerías ruidosas
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._updater").addFilter(_TelegramTimedOutFilter())
# El módulo de automatización en INFO — WebGL noise y mensajes ignorados quedan en DEBUG
logging.getLogger("automation").setLevel(logging.INFO)
# Excluir del log de acceso de uvicorn los endpoints de polling de la UI
logging.getLogger("uvicorn.access").addFilter(_UvicornPollingFilter())
logger = logging.getLogger(__name__)

_tg_apps: list[Application] = []


async def _start_tg_bot(cfg: dict) -> tuple | None:
    """
    Inicializa, arranca y pone en polling un bot de Telegram.
    Maneja timeouts de red con retry exponencial en cada fase.
    Retorna (tg_app, session_id, bot_info) o None si no se pudo conectar.
    """
    token_id = cfg["token"].split(":")[0]
    session_id = f"{cfg['connection_id']}-tg-{token_id}"
    label = f"[{cfg['connection_id']}/tg-{token_id}]"
    tg_app = build_telegram_app(cfg)

    # initialize() llama a get_me() — puede dar timeout si Telegram no responde.
    for attempt in range(3):
        try:
            await tg_app.initialize()
            break
        except Exception as e:
            if attempt < 2:
                wait = 2 ** attempt + random.random() * 2
                logger.warning(
                    f"{label} Timeout al verificar token con Telegram "
                    f"(intento {attempt + 1}/3): reintentando en {wait:.1f}s..."
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"{label} No se pudo inicializar el bot tras 3 intentos "
                    f"({type(e).__name__}). "
                    f"Causas probables: sin acceso a api.telegram.org o token inválido. "
                    f"El bot se omite — el servidor arranca sin él."
                )
                return None

    try:
        await tg_app.start()
    except Exception as e:
        logger.error(
            f"{label} Error al arrancar el dispatcher ({type(e).__name__}: {e}). "
            f"El bot se omite."
        )
        try:
            await tg_app.shutdown()
        except Exception:
            pass
        return None

    # Polling con retry y backoff exponencial
    last_err = None
    for attempt in range(3):
        try:
            await tg_app.updater.start_polling(drop_pending_updates=True)
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                wait = 2 ** attempt + random.random() * 2
                logger.warning(
                    f"{label} Error al iniciar polling "
                    f"(intento {attempt + 1}/3): {e}. Reintentando en {wait:.1f}s..."
                )
                await asyncio.sleep(wait)

    if last_err is not None:
        logger.error(
            f"{label} No se pudo iniciar polling tras 3 intentos: {last_err}. "
            f"El bot se omite."
        )
        await tg_app.stop()
        await tg_app.shutdown()
        return None

    try:
        bot_info = await tg_app.bot.get_me()
    except Exception as e:
        logger.error(f"{label} Error obteniendo info del bot: {e}. El bot se omite.")
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        return None

    return tg_app, session_id, bot_info


async def _seed_pulpo_google_connection():
    """Si GOOGLE_SERVICE_ACCOUNT_JSON está en .env y no existe 'pulpo-default', lo crea."""
    import json as _json
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_json:
        return
    if await google_connection_exists("pulpo-default"):
        return
    try:
        info = _json.loads(sa_json)
        email = info.get("client_email", "")
        if not email:
            logger.warning("[google] GOOGLE_SERVICE_ACCOUNT_JSON no tiene client_email, no se crea pulpo-default")
            return
        await create_google_connection(
            id="pulpo-default",
            bot_id=None,
            credentials_json=sa_json,
            email=email,
            label="Cuenta Pulpo",
        )
        logger.info(f"[google] Conexión pulpo-default creada: {email}")
    except Exception as e:
        logger.error(f"[google] Error creando pulpo-default: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arranque
    await init_db()
    await seed_default_flows()
    await _seed_pulpo_google_connection()
    logger.info("DB lista.")

    if sim_engine.SIM_MODE:
        logger.info("Modo SIMULADO — bots reales desactivados (ENABLE_BOTS != true).")
        config = load_config()
        for bot in config.get("bots", []):
            for tg in bot.get("telegram", []):
                token_id = tg["token"].split(":")[0]
                session_id = f"{bot['id']}-tg-{token_id}"
                sim_engine.sim_connect(session_id, bot["id"])
                logger.info(f"[sim] Auto-conectado TG: {session_id} ({bot['name']})")
    else:
        config = load_config()
        tg_configs = get_telegram_connections(config)

        for cfg in tg_configs:
            result = await _start_tg_bot(cfg)
            if result is None:
                continue
            tg_app, session_id, bot_info = result
            clients[session_id] = {
                "status": "ready", "qr": None,
                "connection_id": cfg["connection_id"], "type": "telegram",
                "client": tg_app,
                "bot_username": bot_info.username or "",
                "bot_name": bot_info.first_name or "",
            }
            _tg_apps.append(tg_app)
            token_id = cfg["token"].split(":")[0]
            logger.info(
                f"[{cfg['connection_id']}/tg-{token_id}] Bot de Telegram listo — @{bot_info.username}."
            )

        if not tg_configs:
            logger.warning("No hay bots de Telegram configurados en connections.json.")

        wavi_poller.start()
        logger.info("[wavi-poll] scheduler arrancado")

    yield

    # Apagado
    if not sim_engine.SIM_MODE:
        for tg_app in _tg_apps:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        logger.info("Bots de Telegram detenidos.")
        await wavi_poller.stop()


from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

app = FastAPI(title="Pulpo API", lifespan=lifespan)
app.state.limiter = bot_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_frontend_port = os.environ.get("FRONTEND_PORT", "5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{_frontend_port}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rutas API ---
app.include_router(auth_router, prefix="/api")
app.include_router(bots_router, prefix="/api")
app.include_router(connections_router, prefix="/api")
app.include_router(telegram_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(sim_router, prefix="/api")
app.include_router(client_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(auth_bot_router, prefix="/api")
app.include_router(bot_portal_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")
app.include_router(summarizer_router, prefix="/api")
app.include_router(flows_router, prefix="/api")
app.include_router(fb_session_router, prefix="/api")
app.include_router(wavi_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(architecture_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "bots": len(_tg_apps)}
