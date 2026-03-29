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


def _tool_applies(tool: dict, contact_id: int | None) -> bool:
    """¿Aplica esta herramienta a este contacto?"""
    excluded_ids = [c["id"] for c in tool["contactos_excluidos"]]
    included_ids = [c["id"] for c in tool["contactos_incluidos"]]

    if contact_id and contact_id in excluded_ids:
        return False
    if contact_id and contact_id in included_ids:
        return True
    if contact_id is None and tool["incluir_desconocidos"]:
        return True
    if not included_ids and tool["incluir_desconocidos"]:
        return True
    return False


async def resolve_tools(bot_id: str, sender: str, channel_type: str) -> tuple[list[dict], dict | None]:
    """
    Retorna (summarizers, reply_tool) para este (bot_id, sender).
    - summarizers: lista de herramientas tipo 'summarizer' que aplican (para acumular)
    - reply_tool: primera herramienta no-summarizer que aplica (para responder), o None
    """
    from config import get_empresas_for_bot
    from db import find_contact_by_channel, get_active_tools_for_bot

    empresa_ids = get_empresas_for_bot(bot_id)
    if not empresa_ids:
        return [], None

    contact = await find_contact_by_channel(channel_type, sender)
    contact_id = contact["id"] if contact else None

    summarizers: list[dict] = []
    reply_tool: dict | None = None

    for empresa_id in empresa_ids:
        tools = await get_active_tools_for_bot(bot_id, empresa_id)
        for tool in tools:
            if not _tool_applies(tool, contact_id):
                continue
            if tool["tipo"] == "summarizer":
                summarizers.append(tool)
            elif reply_tool is None:
                reply_tool = tool

    return summarizers, reply_tool


async def resolve_tool(bot_id: str, sender: str, channel_type: str) -> dict | None:
    """Compatibilidad: retorna solo la primera herramienta de respuesta (no summarizer)."""
    _, reply_tool = await resolve_tools(bot_id, sender, channel_type)
    return reply_tool


async def sim_receive(
    session_id: str,
    from_name: str,
    from_phone: str,
    text: str,
    audio_path: str | None = None,
) -> str | None:
    """
    Procesa un mensaje entrante simulado por el pipeline real:
      1. Guarda en DB bajo TODAS las empresas que tienen esta conexión (dispatch multi-empresa).
      2. Evalúa herramientas y auto_reply para la empresa dueña de la sesión.
    Si se pasa audio_path, transcribe el audio y lo acumula con tipo "audio".
    Devuelve el texto de la respuesta, o None si no hay reply.
    """
    from db import log_message, mark_answered, log_outbound_message
    from config import get_empresas_for_bot

    cfg = _get_phone_config(session_id)
    if not cfg:
        return None

    ts = datetime.now().strftime("%H:%M:%S")
    conv = _conversations.setdefault(session_id, [])

    # Detectar tipo de canal según session_id
    channel_type = "telegram" if "-tg-" in session_id else "whatsapp"

    # Dispatch multi-empresa: loguar bajo todos los bots que tienen esta conexión
    empresa_ids = get_empresas_for_bot(session_id)
    if not empresa_ids:
        # Fallback: usar solo el bot dueño de la sesión
        empresa_ids = [cfg["bot_id"]]

    msg_ids = {}
    for eid in empresa_ids:
        mid = await log_message(eid, session_id, from_phone, from_name, text)
        msg_ids[eid] = mid

    conv.append({"role": "user", "text": text, "from_name": from_name, "ts": ts})
    logger.info("[sim] MSG ← %s (%s) → %s: %s", from_name, from_phone, session_id, text)

    # Motor de resolución: herramientas en DB
    summarizers, reply_tool = await resolve_tools(session_id, from_phone, channel_type)

    # Sumarizadoras: acumular bajo cada empresa que las define
    if summarizers:
        from tools import summarizer as summarizer_mod

        # Transcribir audio si se proporcionó
        if audio_path:
            from tools import transcription as transcription_mod
            transcribed = await transcription_mod.transcribe(audio_path)
            logger.info("[sim] AUDIO transcrito de %s: %s", from_phone, transcribed[:80])
        else:
            transcribed = None

        for s_tool in summarizers:
            if transcribed is not None:
                summarizer_mod.accumulate(
                    empresa_id=s_tool["empresa_id"],
                    contact_phone=from_phone,
                    contact_name=from_name,
                    msg_type="audio",
                    content=transcribed,
                )
                logger.info("[sim] SUMMARIZER '%s' acumuló audio de %s", s_tool["nombre"], from_phone)
            else:
                summarizer_mod.accumulate(
                    empresa_id=s_tool["empresa_id"],
                    contact_phone=from_phone,
                    contact_name=from_name,
                    msg_type="texto",
                    content=text,
                )
                logger.info("[sim] SUMMARIZER '%s' acumuló de %s", s_tool["nombre"], from_phone)

    reply = None
    if reply_tool:
        if reply_tool["tipo"] == "fixed_message":
            reply = reply_tool["config"].get("message", "")
        elif reply_tool["tipo"] == "assistant":
            context = reply_tool["config"].get("prompt", "")
            if context:
                from tools import assistant as assistant_mod
                bot_name = cfg.get("bot_name", "el asistente")
                reply = await assistant_mod.ask(context, text, bot_name)
        elif reply_tool["tipo"] == "flow":
            graph_name = reply_tool["config"].get("graph", "")
            if graph_name == "luganense":
                from graphs import luganense as luganense_graph
                bot_name = cfg.get("bot_name", "el asistente")
                prompt = reply_tool["config"].get("prompt", "")
                empresa_id = reply_tool.get("empresa_id", "")
                reply = await luganense_graph.invoke(
                    text, prompt, bot_name, empresa_id,
                    cliente_phone=from_phone, canal=channel_type,
                )
        logger.info("[sim] TOOL '%s' → %s", reply_tool["nombre"], session_id)

    if reply:
        for mid in msg_ids.values():
            await mark_answered(mid)
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
                return {"bot_id": bot["id"], "bot_name": bot.get("name", bot["id"])}
        # Telegram bots — session_id = "{bot_id}-tg-{token_id}"
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            if f"{bot['id']}-tg-{token_id}" == session_id:
                return {"bot_id": bot["id"], "bot_name": bot.get("name", bot["id"])}
    return None
