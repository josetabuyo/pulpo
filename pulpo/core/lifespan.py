import asyncio
import logging
import os
import random
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


async def _start_tg_bot(cfg: dict, build_telegram_app, clients: dict) -> tuple | None:
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
    from pulpo.core.db import google_connection_exists, create_google_connection

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
async def pulpo_lifespan(app):
    from pulpo.core.db import init_db
    from pulpo.core.config import load_config, get_telegram_connections
    from pulpo.core.state import clients, wavi_status

    await init_db()
    logger.info("DB lista.")

    from pulpo.core import sim_engine, wavi_poller

    # seed default flows (no-op)
    from pulpo.business.flows import seed_default_flows
    seed_default_flows()

    # seed google connection
    await _seed_pulpo_google_connection()

    if sim_engine.SIM_MODE:
        logger.info("Modo SIMULADO — bots reales desactivados.")
        config = load_config()
        for bot in config.get("bots", []):
            for tg in bot.get("telegram", []):
                token_id = tg["token"].split(":")[0]
                session_id = f"{bot['id']}-tg-{token_id}"
                sim_engine.sim_connect(session_id, bot["id"])
                logger.info(f"[sim] Auto-conectado TG: {session_id} ({bot['name']})")
    else:
        from pulpo.bots.telegram_bot import build_telegram_app
        config = load_config()
        tg_configs = get_telegram_connections(config)
        _tg_apps = []

        for cfg in tg_configs:
            result = await _start_tg_bot(cfg, build_telegram_app, clients)
            if result:
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

        import pulpo.tools.wavi_driver as wd_init
        import json as _json
        for _s in wd_init.list_session_names():
            _st = "ready" if wd_init.daemon_running_by_pid(_s) else "stopped"
            wavi_status[_s] = _st
            logger.info("[wavi] startup status %s → %s", _s, _st)
        # Propagar aliases: si "pulpo-bot" → "5491155612767", wavi_status["pulpo-bot"] = wavi_status["5491155612767"]
        _aliases_file = wd_init.WAVI_SESSIONS_DIR / "aliases.json"
        if _aliases_file.exists():
            _aliases = _json.loads(_aliases_file.read_text())
            for _alias, _target in _aliases.items():
                if _alias not in wavi_status and _target in wavi_status:
                    wavi_status[_alias] = wavi_status[_target]
                    logger.info("[wavi] alias %s → %s (%s)", _alias, _target, wavi_status[_alias])

        wavi_poller.start()
        logger.info("[wavi-poll] scheduler arrancado")

        app.state._tg_apps = _tg_apps

    yield

    if not sim_engine.SIM_MODE:
        for tg_app in getattr(app.state, '_tg_apps', []):
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        logger.info("Bots de Telegram detenidos.")
        await wavi_poller.stop()
