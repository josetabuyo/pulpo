"""
Background polling loop for WhatsApp messages via Wavi.
Started from lifespan (production mode only).

Contacts are identified by display name (Wavi's check-updates has no phone numbers).
contact_phone in FlowState holds the display name — consistent with the Wavi driver contract.

Dedup en dos niveles:
  L1: set en memoria (rápido, se pierde en restart)
  L2: tabla wavi_seen en SQLite (sobrevive reinicios — evita re-responder
      el último mensaje de cada chat después de un restart)
"""
import asyncio
import logging

import pulpo.tools.wavi_driver as wd
from pulpo.core.config import get_wa_poll_interval, get_bots_for_connection
from pulpo.core.db import log_message, wavi_msg_hash, wavi_seen_add, wavi_seen_has, wavi_seen_prune
from pulpo.graphs.compiler import dispatch_message
from pulpo.graphs.nodes.state import FlowState
from pulpo.core.state import wavi_status

logger = logging.getLogger(__name__)
_task: asyncio.Task | None = None

# Sesiones suspendidas: check_updates devolvió qr_needed → no reintentar
# hasta que el usuario presione Reconectar (se limpia en cada restart también).
_suspended: set[str] = set()

# L1: (session, contact_name, msg_hash) — cache de la tabla wavi_seen.
_seen: set[tuple[str, str, str]] = set()


def resume_session(session: str) -> None:
    """Quita la sesión de la lista suspendida para que el poller la vuelva a intentar."""
    _suspended.discard(session)


async def _already_seen(session: str, contact: str, text: str) -> bool:
    key = (session, contact, wavi_msg_hash(text))
    if key in _seen:
        return True
    if await wavi_seen_has(*key):
        _seen.add(key)  # calentar L1 para la próxima
        return True
    return False


async def _mark_seen(session: str, contact: str, text: str) -> None:
    key = (session, contact, wavi_msg_hash(text))
    _seen.add(key)
    try:
        await wavi_seen_add(*key)
    except Exception as e:
        # Sin persistencia el dedup sigue funcionando en memoria — no es fatal.
        logger.warning("[wavi-poll] no se pudo persistir dedup %s/%s: %s", session, contact, e)


async def _poll_once():
    for session in wd.list_session_names():
        try:
            await _poll_session(session)
        except Exception:
            # Una sesión rota no debe frenar el resto.
            logger.exception("[wavi-poll] sesión %s falló", session)


async def _poll_session(session: str):
    if session in _suspended:
        logger.debug("[wavi-poll] skip %s — suspended (qr_needed)", session)
        return

    # Fast pid-file check — avoids spawning Chrome just to see if daemon is alive.
    if not wd.daemon_running_by_pid(session):
        wavi_status[session] = "stopped"
        logger.debug("[wavi-poll] skip %s — no pid", session)
        return

    bot_ids = get_bots_for_connection(session)
    if not bot_ids:
        logger.debug("[wavi-poll] skip %s — no bot registered", session)
        return

    result = await wd.check_updates(session)
    if result.get("status") == "error":
        error_str = result.get("error", "")
        if "qr_needed" in error_str or "not authenticated" in error_str:
            _suspended.add(session)
            wavi_status[session] = "disconnected"
            logger.info("[wavi-poll] %s suspendida — auth requerida (esperando Reconectar)", session)
        return

    wavi_status[session] = "ready"
    for contact in result.get("new_inbound", []):
        name = contact.get("name", "")
        preview = contact.get("last_message", "")
        if not name or not preview:
            continue

        # Dedup on the sidebar preview (check-updates signal) — filtro barato
        # para no pedir el detalle completo si no hay nada nuevo.
        if await _already_seen(session, name, preview):
            logger.debug("[wavi-poll] skip duplicate %s/%s", session, name)
            continue

        # Traer varios mensajes recientes (no solo el último) y quedarnos con
        # los que todavía no procesamos, en orden cronológico — una ráfaga de
        # 3 mensajes del usuario entre polls ya no pierde los 2 primeros.
        recent_texts = await wd.get_recent_inbound_texts(session, name)
        if not recent_texts:
            logger.warning("[wavi-poll] get_recent_inbound_texts vacío para %s/%s, usando preview", session, name)
            recent_texts = [preview]

        new_texts = []  # cronológico: más vieja primero
        for text in recent_texts:  # recent_texts viene más nueva primero
            if await _already_seen(session, name, text):
                break  # ya vimos este y todo lo que sigue (más viejo)
            new_texts.append(text)
        new_texts.reverse()
        if not new_texts:
            new_texts = [preview]  # fallback: al menos el que gatilló el poll

        for full_text in new_texts:
            await _mark_seen(session, name, full_text)

            for bot_id in bot_ids:
                try:
                    await log_message(bot_id, session, name, name, full_text)
                except Exception as e:
                    logger.warning("[wavi-poll] log_message error: %s", e)

            state = FlowState(
                message=full_text,
                message_type="text",
                contact_phone=name,
                contact_name=name,
                canal="wavi",
                connection_id=session,
            )
            try:
                state = await dispatch_message(state, connection_id=session)
            except Exception:
                logger.exception("[wavi-poll] dispatch_message error for %s/%s", session, name)
                continue

            reply = state.data.get("reply") or ""
            if reply:
                try:
                    await wd.send(session, name, reply)
                    for bot_id in bot_ids:
                        await log_message(bot_id, session, name, "Bot", reply, outbound=True)
                    await _mark_seen(session, name, reply)  # dedup the outbound too
                except Exception:
                    logger.exception("[wavi-poll] send error for %s/%s", session, name)


async def _loop():
    logger.info("[wavi-poll] scheduler iniciado")
    try:
        pruned = await wavi_seen_prune()
        if pruned:
            logger.info("[wavi-poll] dedup prune: %d entradas viejas eliminadas", pruned)
    except Exception as e:
        logger.warning("[wavi-poll] prune de dedup falló: %s", e)
    while True:
        interval = get_wa_poll_interval()
        try:
            await _poll_once()
        except Exception:
            logger.exception("[wavi-poll] ciclo falló")
        await asyncio.sleep(interval)


def start() -> asyncio.Task:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
    return _task


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
