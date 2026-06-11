"""
Background polling loop for WhatsApp messages via Wavi.
Started from main.py lifespan (production mode only).

Contacts are identified by display name (Wavi's check-updates has no phone numbers).
contact_phone in FlowState holds the display name — consistent with the Wavi driver contract.
"""
import asyncio
import logging

import tools.wavi_driver as wd
from config import get_wa_poll_interval, get_empresas_for_connection
from graphs.compiler import run_flows
from graphs.nodes.state import FlowState
from db import log_message

logger = logging.getLogger(__name__)
_task: asyncio.Task | None = None

# In-memory dedup: (session, contact_name, message_text) → True, cleared each restart.
# Prevents re-triggering the same message if the sidebar snapshot doesn't advance.
_seen: set[tuple[str, str, str]] = set()


async def _poll_once():
    for session in wd.list_session_names():
        # Fast pid-file check — avoids spawning Chrome just to see if daemon is alive.
        if not wd.daemon_running_by_pid(session):
            logger.debug("[wavi-poll] skip %s — no pid", session)
            continue

        empresa_ids = get_empresas_for_connection(session)
        if not empresa_ids:
            logger.debug("[wavi-poll] skip %s — no empresa registered", session)
            continue

        try:
            result = await wd.check_updates(session)
        except Exception as e:
            logger.warning("[wavi-poll] check_updates error for %s: %s", session, e)
            continue

        if result.get("status") == "error":
            continue

        for contact in result.get("new_inbound", []):
            name = contact.get("name", "")
            text = contact.get("last_message", "")
            if not name or not text:
                continue

            dedup_key = (session, name, text)
            if dedup_key in _seen:
                logger.debug("[wavi-poll] skip duplicate %s/%s", session, name)
                continue
            _seen.add(dedup_key)

            for empresa_id in empresa_ids:
                try:
                    await log_message(empresa_id, session, name, name, text)
                except Exception as e:
                    logger.warning("[wavi-poll] log_message error: %s", e)

            state = FlowState(
                message=text,
                message_type="text",
                contact_phone=name,
                contact_name=name,
                canal="wavi",
                connection_id=session,
            )
            try:
                state = await run_flows(state, connection_id=session)
            except Exception as e:
                logger.error("[wavi-poll] run_flows error for %s/%s: %s", session, name, e)
                continue

            reply = state.reply or ""
            if reply:
                try:
                    await wd.send(session, name, reply)
                    for empresa_id in empresa_ids:
                        await log_message(empresa_id, session, name, "Bot", reply, outbound=True)
                    _seen.add((session, name, reply))  # dedup the outbound too
                except Exception as e:
                    logger.error("[wavi-poll] send error for %s/%s: %s", session, name, e)


async def _loop():
    logger.info("[wavi-poll] scheduler iniciado")
    while True:
        interval = get_wa_poll_interval()
        try:
            await _poll_once()
        except Exception as e:
            logger.error("[wavi-poll] ciclo falló: %s", e)
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
