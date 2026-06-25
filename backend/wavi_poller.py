"""
Background polling loop for WhatsApp messages via Wavi.
Started from main.py lifespan (production mode only).

Contacts are identified by display name (Wavi's check-updates has no phone numbers).
contact_phone in FlowState holds the display name — consistent with the Wavi driver contract.

Dedup en dos niveles:
  L1: set en memoria (rápido, se pierde en restart)
  L2: tabla wavi_seen en SQLite (sobrevive reinicios — evita re-responder
      el último mensaje de cada chat después de un restart)
"""
import asyncio
import logging

import tools.wavi_driver as wd
from config import get_wa_poll_interval, get_bots_for_connection
from db import log_message, wavi_msg_hash, wavi_seen_add, wavi_seen_has, wavi_seen_prune
from graphs.compiler import run_flows
from graphs.nodes.state import FlowState

logger = logging.getLogger(__name__)
_task: asyncio.Task | None = None

# L1: (session, contact_name, msg_hash) — cache de la tabla wavi_seen.
_seen: set[tuple[str, str, str]] = set()


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
    # Fast pid-file check — avoids spawning Chrome just to see if daemon is alive.
    if not wd.daemon_running_by_pid(session):
        logger.debug("[wavi-poll] skip %s — no pid", session)
        return

    bot_ids = get_bots_for_connection(session)
    if not bot_ids:
        logger.debug("[wavi-poll] skip %s — no bot registered", session)
        return

    result = await wd.check_updates(session)
    if result.get("status") == "error":
        return

    for contact in result.get("new_inbound", []):
        name = contact.get("name", "")
        preview = contact.get("last_message", "")
        if not name or not preview:
            continue

        # Dedup on the sidebar preview (check-updates signal).
        if await _already_seen(session, name, preview):
            logger.debug("[wavi-poll] skip duplicate %s/%s", session, name)
            continue
        await _mark_seen(session, name, preview)

        # Fetch the full message text via wavi get --newest.
        full_text = await wd.get_last_inbound(session, name)
        if full_text is None:
            logger.warning("[wavi-poll] get_last_inbound failed for %s/%s, falling back to preview", session, name)
            full_text = preview

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
            state = await run_flows(state, connection_id=session)
        except Exception:
            logger.exception("[wavi-poll] run_flows error for %s/%s", session, name)
            continue

        reply = state.reply or ""
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
