import asyncio
import logging
import time
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from pulpo.core.db import log_message, mark_answered

logger = logging.getLogger(__name__)

_SEND_MAX_RETRIES = 3
_SEND_RETRY_BACKOFF = 1.5  # segundos, se duplica en cada intento

_DISCULPAS_MSG = (
    "Uy, perdón — tuvimos un problema técnico y no pudimos mandarte la respuesta a tiempo. "
    "¿Me lo repetís en un ratito? 🙏"
)


def build_telegram_app(bot_config: dict):
    """
    Construye una Application de python-telegram-bot para un bot dado.
    bot_config: { connection_id, token, reply_message }
    """
    bot_id = bot_config["connection_id"]
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

        # Detectar audio (voice note o archivo de audio)
        is_audio = False
        audio_obj = msg.voice or msg.audio
        if audio_obj and not text:
            is_audio = True
            import os, tempfile
            from pulpo.tools import transcription
            tg_file = await context.bot.get_file(audio_obj.file_id)
            suffix = ".ogg" if msg.voice else ".mp3"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
            try:
                await tg_file.download_to_drive(tmp_path)
                text = await transcription.transcribe(tmp_path)
                logger.info(f"{label} Audio transcrito de {sender_name}: \"{text[:60]}\"")
            except Exception as e:
                logger.warning(f"{label} Error transcribiendo audio: {e}")
                text = "[audio — error al transcribir]"
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        # Dispatch multi-bot: loguar bajo todos los bots que tienen este session_id
        from pulpo.core.config import get_bots_for_connection
        bot_ids = get_bots_for_connection(session_id)
        if not bot_ids:
            bot_ids = [bot_id]

        msg_ids = {}
        for eid in bot_ids:
            mid = await log_message(eid, token_id, sender_id, sender_name, text)
            msg_ids[eid] = mid

        logger.info(f"{label} Mensaje de {sender_name}: \"{text}\"")

        # Flow engine
        from pulpo.graphs.compiler import dispatch_message
        from pulpo.graphs.nodes.state import FlowState

        state = FlowState(
            message=text,
            message_type="audio" if is_audio else "text",
            bot_name="",
            contact_phone=sender_id,
            contact_name=sender_name,
            canal="telegram",
        )
        state = await dispatch_message(state, connection_id=session_id)
        reply = state.data.get("reply") or ""

        # Appendar URLs de fuentes en código (el LLM no lo hace consistentemente)
        source_urls = state.data.get("source_urls", [])
        if source_urls and reply:
            links = "\n".join(
                f"[📎 Ver publicación {i+1}]({u})" for i, u in enumerate(source_urls)
            )
            reply += f"\n\n{links}"

        if not reply or text == reply:
            return

        sent = False
        last_error: Exception | None = None
        for attempt in range(1, _SEND_MAX_RETRIES + 1):
            try:
                await msg.reply_text(reply, parse_mode="Markdown")
                sent = True
                break
            except Exception as e:
                last_error = e
                logger.warning(f"{label}   → Intento {attempt}/{_SEND_MAX_RETRIES} falló al responder: {e}")
                if attempt < _SEND_MAX_RETRIES:
                    await asyncio.sleep(_SEND_RETRY_BACKOFF * attempt)

        if sent:
            for eid, mid in msg_ids.items():
                await mark_answered(mid)
                await log_message(eid, token_id, sender_id, "Bot", reply, outbound=True)
            logger.info(f"{label}   → Respuesta enviada: {reply[:500]}")
            return

        logger.error(f"{label}   → Agotados los {_SEND_MAX_RETRIES} intentos al responder: {last_error}")
        try:
            await msg.reply_text(_DISCULPAS_MSG)
            for eid, mid in msg_ids.items():
                await mark_answered(mid)
                await log_message(eid, token_id, sender_id, "Bot", _DISCULPAS_MSG, outbound=True)
            logger.info(f"{label}   → Disculpas enviadas tras fallo de envío")
        except Exception as e:
            logger.error(f"{label}   → No se pudo ni siquiera enviar el mensaje de disculpas: {e}")

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        err = context.error
        if isinstance(err, NetworkError):
            logger.warning(f"{label} ⚠️ Error de red (Telegram polling): {err.__class__.__name__}: {err}")
        elif isinstance(err, TimedOut):
            logger.warning(f"{label} ⚠️ Timeout en polling de Telegram")
        else:
            logger.error(f"{label} Error inesperado en bot Telegram: {err.__class__.__name__}", exc_info=err)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_error_handler(error_handler)
    return app
