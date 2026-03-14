import logging
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from db import log_message, mark_answered
from config import load_config, get_telegram_bots

logger = logging.getLogger(__name__)


def build_telegram_app(bot_config: dict):
    """
    Construye una Application de python-telegram-bot para un bot dado.
    bot_config: { bot_id, token, allowed_contacts, reply_message }
    """
    bot_id = bot_config["bot_id"]
    token = bot_config["token"]
    token_id = token.split(":")[0]
    label = f"[{bot_id}/tg-{token_id}]"
    start_time = time.time()

    def _get_live_config():
        """Lee la config fresca de disco para obtener allowed y reply_message actuales."""
        for entry in get_telegram_bots(load_config()):
            if entry["token"] == token:
                return entry["allowed_contacts"], entry["reply_message"]
        return bot_config["allowed_contacts"], bot_config["reply_message"]

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        if not msg:
            return

        # Ignorar mensajes anteriores al arranque
        if msg.date.timestamp() < start_time:
            return

        allowed, reply_message = _get_live_config()

        if not allowed:
            return

        sender = msg.from_user
        sender_username = (sender.username or "").lower()
        sender_id = str(sender.id)
        sender_name = sender.username or sender.first_name or sender_id

        if sender_username not in allowed and sender_id not in allowed:
            return

        text = msg.text or ""
        if text == reply_message:
            return

        msg_id = await log_message(bot_id, token_id, sender_id, sender_name, text)
        logger.info(f"{label} Mensaje de {sender_name}: \"{text}\"")

        try:
            await msg.reply_text(reply_message)
            await mark_answered(msg_id)
            logger.info(f"{label}   → Respuesta enviada (id: {msg_id})")
        except Exception as e:
            logger.error(f"{label}   → Error al responder: {e}")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    return app
