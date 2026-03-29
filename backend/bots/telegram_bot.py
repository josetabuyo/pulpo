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
        from config import get_empresas_for_bot
        empresa_ids = get_empresas_for_bot(session_id)
        if not empresa_ids:
            empresa_ids = [bot_id]

        msg_ids = {}
        for eid in empresa_ids:
            mid = await log_message(eid, token_id, sender_id, sender_name, text)
            msg_ids[eid] = mid

        logger.info(f"{label} Mensaje de {sender_name}: \"{text}\"")

        # Motor de resolución: herramientas en DB
        from sim import resolve_tools
        from datetime import datetime
        summarizers, tool = await resolve_tools(session_id, sender_id, "telegram")

        if summarizers:
            from tools import summarizer as summarizer_mod
            for s_tool in summarizers:
                summarizer_mod.accumulate(
                    empresa_id=s_tool["empresa_id"],
                    contact_phone=sender_id,
                    contact_name=sender_name,
                    msg_type="audio" if is_audio else "text",
                    content=text,
                    timestamp=datetime.now(),
                )

        if not tool:
            logger.debug(f"{label} Sin herramienta activa para {sender_name} ({sender_id})")
            return

        if tool["tipo"] == "fixed_message":
            reply = tool["config"].get("message", "")
        elif tool["tipo"] == "assistant":
            context = tool["config"].get("prompt", "")
            if context:
                from tools import assistant as assistant_mod
                from config import load_config
                cfg = load_config()
                bot_entry = next((b for b in cfg.get("bots", []) if b["id"] == bot_id), {})
                reply = await assistant_mod.ask(context, text, bot_entry.get("name", bot_id)) or ""
            else:
                reply = ""
        elif tool["tipo"] == "flow":
            graph_name = tool["config"].get("graph", "")
            if graph_name == "luganense":
                from graphs import luganense as luganense_graph
                from config import load_config
                cfg = load_config()
                bot_entry = next((b for b in cfg.get("bots", []) if b["id"] == bot_id), {})
                bot_name = bot_entry.get("name", bot_id)
                prompt = tool["config"].get("prompt", "")
                empresa_id = tool.get("empresa_id", "")
                reply = await luganense_graph.invoke(
                    text, prompt, bot_name, empresa_id,
                    cliente_phone=sender_id, canal="telegram",
                )
            else:
                reply = ""
        else:
            reply = ""

        if not reply or text == reply:
            return

        try:
            await msg.reply_text(reply)
            for mid in msg_ids.values():
                await mark_answered(mid)
            logger.info(f"{label}   → Respuesta enviada")
        except Exception as e:
            logger.error(f"{label}   → Error al responder: {e}")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    return app
