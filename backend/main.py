import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from telegram.ext import Application

from config import load_config, get_telegram_bots
from db import init_db
from bots.telegram_bot import build_telegram_app
from state import clients

from api.auth import router as auth_router
from api.bots import router as bots_router
from api.phones import router as phones_router
from api.telegram_api import router as telegram_router
from api.whatsapp import router as whatsapp_router
from api.messages import router as messages_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_tg_apps: list[Application] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arranque
    await init_db()
    logger.info("DB lista.")

    config = load_config()
    tg_configs = get_telegram_bots(config)

    for cfg in tg_configs:
        token_id = cfg["token"].split(":")[0]
        session_id = f"{cfg['bot_id']}-tg-{token_id}"
        tg_app = build_telegram_app(cfg)
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        _tg_apps.append(tg_app)
        clients[session_id] = {"status": "ready", "qr": None, "bot_id": cfg["bot_id"], "type": "telegram", "client": tg_app}
        logger.info(f"[{cfg['bot_id']}/tg-{token_id}] Bot de Telegram listo.")

    if not tg_configs:
        logger.warning("No hay bots de Telegram configurados en phones.json.")

    yield

    # Apagado
    for tg_app in _tg_apps:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
    logger.info("Bots de Telegram detenidos.")


app = FastAPI(title="Bot Farm API", lifespan=lifespan)

# --- Rutas API ---
app.include_router(auth_router, prefix="/api")
app.include_router(bots_router, prefix="/api")
app.include_router(phones_router, prefix="/api")
app.include_router(telegram_router, prefix="/api")
app.include_router(whatsapp_router, prefix="/api")
app.include_router(messages_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "bots": len(_tg_apps)}


# --- Archivos estáticos (dashboard HTML) ---
_PUBLIC = Path(__file__).parent.parent / "public"
if _PUBLIC.exists():
    app.mount("/", StaticFiles(directory=str(_PUBLIC), html=True), name="static")
