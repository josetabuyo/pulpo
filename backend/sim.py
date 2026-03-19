"""
Simulador de bots — activo cuando ENABLE_BOTS != "true" (worktrees de dev).

Mantiene conversaciones en memoria y procesa mensajes por el mismo
pipeline real (log_message, mark_answered, auto_reply) sin tocar
WhatsApp ni Telegram.
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


async def resolve_tool(bot_id: str, sender: str, channel_type: str) -> dict | None:
    """
    Retorna la primera herramienta activa que aplica a este (bot_id, sender).
    Evalúa todas las empresas que tienen este bot_id (conexión compartida).
    Fallback: None.
    """
    from config import get_empresas_for_bot
    from db import find_contact_by_channel, get_active_tools_for_bot

    empresa_ids = get_empresas_for_bot(bot_id)
    if not empresa_ids:
        return None

    contact = await find_contact_by_channel(channel_type, sender)
    contact_id = contact["id"] if contact else None

    for empresa_id in empresa_ids:
        tools = await get_active_tools_for_bot(bot_id, empresa_id)
        for tool in tools:
            excluded_ids = [c["id"] for c in tool["contactos_excluidos"]]
            included_ids = [c["id"] for c in tool["contactos_incluidos"]]

            # Regla 1: excluido → saltar
            if contact_id and contact_id in excluded_ids:
                continue

            # Regla 2: incluido explícitamente → activar
            if contact_id and contact_id in included_ids:
                return tool

            # Regla 3: desconocido + incluir_desconocidos → activar
            if contact_id is None and tool["incluir_desconocidos"]:
                return tool

            # Regla 4: lista incluidos vacía + incluir_desconocidos → activar para todos
            if not included_ids and tool["incluir_desconocidos"]:
                return tool

    return None


async def _is_sender_allowed(bot_id: str, channel_type: str, sender: str) -> bool:
    """Retorna True si el sender tiene un contacto registrado en DB."""
    from db import find_contact_by_channel
    contact = await find_contact_by_channel(channel_type, sender)
    return contact is not None


async def sim_receive(session_id: str, from_name: str, from_phone: str, text: str) -> str | None:
    """
    Procesa un mensaje entrante simulado por el pipeline real:
      1. Guarda en DB (siempre, para sugeridos).
      2. Verifica si el sender es un contacto permitido.
      3. Si está permitido, responde con auto_reply.
    Devuelve el texto de la respuesta, o None si no hay auto_reply o no está permitido.
    """
    from db import log_message, mark_answered, log_outbound_message

    cfg = _get_phone_config(session_id)
    if not cfg:
        return None

    ts = datetime.now().strftime("%H:%M:%S")
    conv = _conversations.setdefault(session_id, [])

    # Detectar tipo de canal según session_id
    channel_type = "telegram" if "-tg-" in session_id else "whatsapp"

    # Guardar en DB siempre (para que aparezca en sugeridos)
    msg_id = await log_message(cfg["bot_id"], session_id, from_phone, from_name, text)
    conv.append({"role": "user", "text": text, "from_name": from_name, "ts": ts})
    logger.info("[sim] MSG ← %s (%s) → %s: %s", from_name, from_phone, session_id, text)

    # Verificar si el sender está permitido
    allowed = await _is_sender_allowed(cfg["bot_id"], channel_type, from_phone)
    if not allowed:
        logger.info("[sim] IGNORADO (no es contacto registrado) → %s", from_phone)
        return None

    # Motor de resolución: herramientas en DB
    tool = await resolve_tool(session_id, from_phone, channel_type)
    if tool:
        if tool["tipo"] == "fixed_message":
            reply = tool["config"].get("message", "")
        else:
            reply = None
        logger.info("[sim] TOOL '%s' → %s", tool["nombre"], session_id)
    else:
        # Fallback: auto_reply del JSON
        reply = cfg["auto_reply"]

    if reply:
        await mark_answered(msg_id)
        await log_outbound_message(cfg["bot_id"], session_id, from_phone, reply)
        conv.append({"role": "bot", "text": reply, "from_name": "Bot", "ts": ts})
        logger.info("[sim] REPLY → %s: %s", session_id, reply[:80])

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
