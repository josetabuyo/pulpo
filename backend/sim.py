"""
Simulador de bots — activo cuando ENABLE_BOTS != "true" (worktrees de dev).

Mantiene conversaciones en memoria y procesa mensajes por el mismo
pipeline real (log_message, mark_answered, auto_reply) sin tocar
WhatsApp ni Telegram.
"""

import os
from datetime import datetime

SIM_MODE = os.environ.get("ENABLE_BOTS", "true").lower() != "true"

# { session_id: [{ role, text, from_name, ts }] }
_conversations: dict[str, list] = {}


def get_mode() -> str:
    return "sim" if SIM_MODE else "real"


def sim_connect(session_id: str, bot_id: str) -> None:
    """Marca la sesión como lista instantáneamente (sin browser)."""
    from state import clients
    clients[session_id] = {
        "status": "ready",
        "qr": None,
        "bot_id": bot_id,
        "type": "whatsapp",
        "client": None,
    }
    _conversations.setdefault(session_id, [])


def sim_disconnect(session_id: str) -> None:
    from state import clients
    clients.pop(session_id, None)
    _conversations.pop(session_id, None)


async def sim_receive(session_id: str, from_name: str, from_phone: str, text: str) -> str | None:
    """
    Procesa un mensaje entrante simulado por el pipeline real:
      1. Guarda en DB (igual que WA real).
      2. Responde con el auto_reply del teléfono/bot.
      3. Guarda la respuesta como answered.
    Devuelve el texto de la respuesta, o None si no hay auto_reply.
    """
    from db import log_message, mark_answered, log_outbound_message

    cfg = _get_phone_config(session_id)
    if not cfg:
        return None

    ts = datetime.now().strftime("%H:%M:%S")
    conv = _conversations.setdefault(session_id, [])

    msg_id = await log_message(cfg["bot_id"], session_id, from_phone, from_name, text)
    conv.append({"role": "user", "text": text, "from_name": from_name, "ts": ts})

    reply = cfg["auto_reply"]
    if reply:
        await mark_answered(msg_id)
        await log_outbound_message(cfg["bot_id"], session_id, from_phone, reply)
        conv.append({"role": "bot", "text": reply, "from_name": "Bot", "ts": ts})

    return reply or None


def get_conversation(session_id: str) -> list:
    return _conversations.get(session_id, [])


def _get_phone_config(session_id: str) -> dict | None:
    from config import load_config
    config = load_config()
    for bot in config.get("bots", []):
        # WhatsApp phones
        for phone in bot.get("phones", []):
            if phone["number"] == session_id:
                return {
                    "bot_id": bot["id"],
                    "auto_reply": phone.get("autoReplyMessage") or bot.get("autoReplyMessage", ""),
                }
        # Telegram bots — session_id = "{bot_id}-tg-{token_id}"
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            if f"{bot['id']}-tg-{token_id}" == session_id:
                return {
                    "bot_id": bot["id"],
                    "auto_reply": tg.get("autoReplyMessage") or bot.get("autoReplyMessage", ""),
                }
    return None
