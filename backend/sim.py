"""
Simulador de bots — activo cuando ENABLE_BOTS != "true" (worktrees de dev).

Mantiene conversaciones en memoria y procesa mensajes por el mismo
pipeline real (log_message, mark_answered, auto_reply) sin tocar Telegram real.
"""

import logging
import os
from datetime import datetime

SIM_MODE = os.environ.get("ENABLE_BOTS", "true").lower() != "true"
logger = logging.getLogger(__name__)

# { session_id: [{ role, text, from_name, ts }] }
_conversations: dict[str, list] = {}


def get_mode() -> str:
    return "sim" if SIM_MODE else "real"


def sim_connect(session_id: str, connection_id: str) -> None:
    """Marca la sesión como lista instantáneamente (sin browser)."""
    from state import clients
    clients[session_id] = {
        "status": "ready",
        "qr": None,
        "connection_id": connection_id,
        "type": "telegram",
        "client": None,
    }
    _conversations.setdefault(session_id, [])


def sim_disconnect(session_id: str) -> None:
    from state import clients
    clients.pop(session_id, None)
    _conversations.pop(session_id, None)




async def sim_receive(
    session_id: str,
    from_name: str,
    from_phone: str,
    text: str,
    audio_path: str | None = None,
) -> str | None:
    """
    Procesa un mensaje entrante simulado por el pipeline real:
      1. Guarda en DB bajo TODAS las bots que tienen esta conexión (dispatch multi-bot).
      2. Evalúa herramientas y auto_reply para la bot dueña de la sesión.
    Si se pasa audio_path, transcribe el audio y lo acumula con tipo "audio".
    Devuelve el texto de la respuesta, o None si no hay reply.
    """
    from db import log_message, mark_answered, log_outbound_message
    from config import get_bots_for_connection

    cfg = _get_phone_config(session_id)
    if not cfg:
        return None

    ts = datetime.now().strftime("%H:%M:%S")
    conv = _conversations.setdefault(session_id, [])

    channel_type = "telegram"

    # Dispatch multi-bot: loguar bajo todos los bots que tienen esta conexión
    bot_ids = get_bots_for_connection(session_id)
    if not bot_ids:
        # Fallback: usar solo el bot dueño de la sesión
        bot_ids = [cfg["connection_id"]]

    msg_ids = {}
    for eid in bot_ids:
        mid = await log_message(eid, session_id, from_phone, from_name, text)
        msg_ids[eid] = mid

    conv.append({"role": "user", "text": text, "from_name": from_name, "ts": ts})
    logger.info("[sim] MSG ← %s (%s) → %s: %s", from_name, from_phone, session_id, text)

    # Transcribir audio si se proporcionó
    msg_type = "text"
    if audio_path:
        from tools import transcription as transcription_mod
        text = await transcription_mod.transcribe(audio_path)
        msg_type = "audio"
        logger.info("[sim] AUDIO transcrito de %s: %s", from_phone, text[:80])

    # Flow engine
    from graphs.compiler import run_flows
    from graphs.nodes.state import FlowState

    state = FlowState(
        message=text,
        message_type=msg_type,
        bot_name=cfg.get("bot_name", ""),
        contact_phone=from_phone,
        contact_name=from_name,
        canal=channel_type,
    )
    state = await run_flows(state, connection_id=session_id)
    reply = state.data.get("reply")

    if reply:
        for mid in msg_ids.values():
            await mark_answered(mid)
        await log_outbound_message(cfg["connection_id"], session_id, from_phone, reply)
        from graphs.nodes.summarize import accumulate as _accumulate
        _accumulate(
            bot_id=cfg["connection_id"],
            contact_phone=from_phone,
            contact_name=from_name,
            msg_type="text",
            content=f"Tú: {reply}",
        )
        conv.append({"role": "bot", "text": reply, "from_name": "Bot", "ts": ts})
        logger.info("[sim] REPLY → %s: %s", session_id, reply[:80])

    return reply or None


def get_conversation(session_id: str) -> list:
    return _conversations.get(session_id, [])


def _get_phone_config(session_id: str) -> dict | None:
    from config import load_config
    config = load_config()
    for bot in config.get("bots", []):
        # Telegram bots — session_id = "{connection_id}-tg-{token_id}"
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            if f"{bot['id']}-tg-{token_id}" == session_id:
                return {"connection_id": bot["id"], "bot_name": bot.get("name", bot["id"])}
    return None
