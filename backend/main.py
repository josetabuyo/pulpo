import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telegram.ext import Application

from pathlib import Path

from config import load_config, get_telegram_connections
from db import init_db
from bots.telegram_bot import build_telegram_app
from state import clients, wa_session
from api.whatsapp import _connect_and_get_qr, _get_wa_config

from api.whatsapp import _run_delta_sync
from api.auth import router as auth_router
from api.auth_empresa import router as auth_empresa_router, limiter as empresa_limiter
from api.bots import router as bots_router
from api.connections import router as connections_router
from api.telegram_api import router as telegram_router
from api.whatsapp import router as whatsapp_router
from api.messages import router as messages_router
from api.sim import router as sim_router
from api.client import router as client_router
from api.logs import router as logs_router
from api.empresa import router as empresa_router
from api.contacts import router as contacts_router
from api.summarizer import router as summarizer_router
from api.flows import router as flows_router, seed_default_flows
from api.fb_session import router as fb_session_router
import sim as sim_engine

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


class _UvicornPollingFilter(logging.Filter):
    """Excluye del log de acceso de uvicorn los endpoints que la UI consulta periódicamente."""
    _POLLING = (
        '"GET /api/bots HTTP',
        '"GET /api/sync-status HTTP',
        '"GET /api/logs/latest',
        '/paused HTTP',          # /api/empresa/{id}/paused
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
# El módulo de automatización en INFO — WebGL noise y mensajes ignorados quedan en DEBUG
logging.getLogger("automation").setLevel(logging.INFO)
# Excluir del log de acceso de uvicorn los endpoints de polling de la UI
logging.getLogger("uvicorn.access").addFilter(_UvicornPollingFilter())
logger = logging.getLogger(__name__)

_tg_apps: list[Application] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arranque
    await init_db()
    await seed_default_flows()
    logger.info("DB lista.")

    if sim_engine.SIM_MODE:
        logger.info("Modo SIMULADO — bots reales desactivados (ENABLE_BOTS != true).")
        config = load_config()
        for empresa in config.get("empresas", []):
            for phone in empresa.get("phones", []):  # desde connections.json
                sim_engine.sim_connect(phone["number"], empresa["id"])
                logger.info(f"[sim] Auto-conectado WA: {phone['number']} ({empresa['name']})")
            for tg in empresa.get("telegram", []):
                token_id = tg["token"].split(":")[0]
                session_id = f"{empresa['id']}-tg-{token_id}"
                sim_engine.sim_connect(session_id, empresa["id"])
                logger.info(f"[sim] Auto-conectado TG: {session_id} ({empresa['name']})")
    else:
        # Limpiar procesos WA huérfanos de reinicios anteriores.
        # Solo matamos los Chrome que tienen data/sessions en su perfil — nunca el MCP.
        import subprocess
        subprocess.run(["pkill", "-f", "data/sessions"], capture_output=True)
        await wa_session.launch()
        logger.info("Browser iniciado.")

        config = load_config()
        tg_configs = get_telegram_connections(config)

        for cfg in tg_configs:
            token_id = cfg["token"].split(":")[0]
            session_id = f"{cfg['connection_id']}-tg-{token_id}"
            tg_app = build_telegram_app(cfg)
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling(drop_pending_updates=True)
            _tg_apps.append(tg_app)
            bot_info = await tg_app.bot.get_me()
            clients[session_id] = {
                "status": "ready", "qr": None,
                "connection_id": cfg["connection_id"], "type": "telegram",
                "client": tg_app,
                "bot_username": bot_info.username or "",
                "bot_name": bot_info.first_name or "",
            }
            logger.info(f"[{cfg['connection_id']}/tg-{token_id}] Bot de Telegram listo — @{bot_info.username}.")

        if not tg_configs:
            logger.warning("No hay bots de Telegram configurados en connections.json.")

        # Auto-reconectar sesiones WA que tienen perfil guardado en disco
        # Deduplicar: un número puede estar en múltiples empresas (conexión compartida)
        seen_numbers: set[str] = set()
        for empresa in config.get("empresas", []):
            for phone in empresa.get("phones", []):  # desde connections.json
                if phone.get("type", "whatsapp") != "whatsapp":
                    continue
                number = phone["number"]
                if number in seen_numbers:
                    continue
                seen_numbers.add(number)
                profile_dir = Path("data/sessions") / number / "profile"
                if profile_dir.exists() and any(profile_dir.iterdir()):
                    logger.info(f"[{number}] Perfil guardado encontrado — reconectando en background...")
                    asyncio.create_task(_connect_and_get_qr(number, empresa["id"]))
                else:
                    logger.info(f"[{number}] Sin perfil guardado — esperando escaneo de QR manual.")

        # Delta sync al arrancar: captura mensajes perdidos desde el último reinicio
        async def _startup_delta_sync():
            await asyncio.sleep(15)  # esperar que los bots reconecten
            await _run_delta_sync()

        asyncio.create_task(_startup_delta_sync())

    yield

    # Apagado
    if not sim_engine.SIM_MODE:
        for tg_app in _tg_apps:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        logger.info("Bots de Telegram detenidos.")
        await wa_session.shutdown()
        logger.info("Browser cerrado.")


from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

app = FastAPI(title="Pulpo API", lifespan=lifespan)
app.state.limiter = empresa_limiter
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
app.include_router(whatsapp_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(sim_router, prefix="/api")
app.include_router(client_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(auth_empresa_router, prefix="/api")
app.include_router(empresa_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")
app.include_router(summarizer_router, prefix="/api")
app.include_router(flows_router, prefix="/api")
app.include_router(fb_session_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "bots": len(_tg_apps)}
