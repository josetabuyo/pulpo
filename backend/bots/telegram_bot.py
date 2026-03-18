import logging
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from db import log_message, mark_answered

logger = logging.getLogger(__name__)


def build_telegram_app(bot_config: dict):
    """
    Construye una Application de python-telegram-bot para un bot dado.
    bot_config: { bot_id, token, reply_message }
    """
    bot_id = bot_config["bot_id"]
    token = bot_config["token"]
    token_id = token.split(":")[0]
    session_id = f"{bot_id}-tg-{token_id}"
    label = f"[{bot_id}/tg-{token_id}]"
    start_time = time.time()

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        if not msg:
            return

        # Ignorar mensajes anteriores al arranque
        if msg.date.timestamp() < start_time:
            return

        sender = msg.from_user
        sender_id = str(sender.id)
        sender_name = sender.username or sender.first_name or sender_id

        text = msg.text or ""

        # Log siempre (para sugeridos)
        msg_id = await log_message(bot_id, token_id, sender_id, sender_name, text)
        logger.info(f"{label} Mensaje de {sender_name}: \"{text}\"")

        # Motor de resolución: herramientas en DB
        from sim import resolve_tool
        tool = await resolve_tool(session_id, sender_id, "telegram")
        if not tool:
            logger.debug(f"{label} Sin herramienta activa para {sender_name} ({sender_id})")
            return

        if tool["tipo"] == "fixed_message":
            reply = tool["config"].get("message", "")
        else:
            reply = ""

        if not reply or text == reply:
            return

        try:
            await msg.reply_text(reply)
            await mark_answered(msg_id)
            logger.info(f"{label}   → Respuesta enviada (id: {msg_id})")
        except Exception as e:
            logger.error(f"{label}   → Error al responder: {e}")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    return app
