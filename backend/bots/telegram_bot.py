import logging
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from db import log_message, mark_answered

logger = logging.getLogger(__name__)


def build_telegram_app(bot_config: dict):
    """
    Construye una Application de python-telegram-bot para un bot dado.
    bot_config: { bot_id, token, allowed_contacts, reply_message }
    """
    bot_id = bot_config["bot_id"]
    token = bot_config["token"]
    token_id = token.split(":")[0]
    allowed = bot_config["allowed_contacts"]
    reply_message = bot_config["reply_message"]
    label = f"[{bot_id}/tg-{token_id}]"
    start_time = time.time()

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        if not msg:
            return

        # Ignorar mensajes anteriores al arranque
        if msg.date.timestamp() < start_time:
            return

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
