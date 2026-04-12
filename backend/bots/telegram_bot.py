import logging
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from db import log_message, mark_answered

logger = logging.getLogger(__name__)


def build_telegram_app(bot_config: dict):
    """
    Construye una Application de python-telegram-bot para un bot dado.
    bot_config: { connection_id, token, reply_message }
    """
    empresa_id = bot_config["connection_id"]
    token = bot_config["token"]
    token_id = token.split(":")[0]
    session_id = f"{empresa_id}-tg-{token_id}"
    label = f"[{empresa_id}/tg-{token_id}]"
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
            from tools import transcription
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

        # Dispatch multi-empresa: loguar bajo todos los bots que tienen este session_id
        from config import get_empresas_for_connection
        empresa_ids = get_empresas_for_connection(session_id)
        if not empresa_ids:
            empresa_ids = [empresa_id]

        msg_ids = {}
        for eid in empresa_ids:
            mid = await log_message(eid, token_id, sender_id, sender_name, text)
            msg_ids[eid] = mid

        logger.info(f"{label} Mensaje de {sender_name}: \"{text}\"")

        # Flow engine
        from graphs.compiler import run_flows
        from graphs.nodes.state import FlowState

        state = FlowState(
            message=text,
            message_type="audio" if is_audio else "text",
            bot_name="",
            contact_phone=sender_id,
            contact_name=sender_name,
            canal="telegram",
        )
        state = await run_flows(state, connection_id=session_id)
        reply = state.reply or ""
        image_url = state.image_url or ""

        # Appendar URLs de fuentes en código (el LLM no lo hace consistentemente)
        source_urls = state.vars.get("source_urls", [])
        if source_urls and reply:
            links = "\n".join(
                f"[📎 Ver publicación {i+1}]({u})" for i, u in enumerate(source_urls)
            )
            reply += f"\n\n{links}"

        if not reply or text == reply:
            return

        try:
            if image_url:
                try:
                    import urllib.request
                    with urllib.request.urlopen(image_url, timeout=10) as resp:
                        image_data = resp.read()
                    await msg.reply_photo(image_data, caption=reply, parse_mode="Markdown")
                    logger.info(f"{label}   → Respuesta con imagen enviada: {reply[:500]}")
                except Exception as img_err:
                    logger.warning(f"{label}   → Error enviando imagen, fallback a texto: {img_err}")
                    await msg.reply_text(reply)
            else:
                await msg.reply_text(reply, parse_mode="Markdown")
            for eid, mid in msg_ids.items():
                await mark_answered(mid)
                await log_message(eid, token_id, sender_id, "Bot", reply, outbound=True)
            logger.info(f"{label}   → Respuesta enviada: {reply[:500]}")
        except Exception as e:
            logger.error(f"{label}   → Error al responder: {e}")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    return app
