"""
Passive message bridge for teli (Telegram) → Pulpo pipeline.

Architecture: INVERTED vs wavi_poller.
  - wavi_poller: active loop that polls WhatsApp for new messages (pull)
  - teli_poller: registers a handler on each teli bot; messages arrive push
                 via teli's long-polling and are forwarded to run_flows.

The bridge:
  Each teli bot runs in a dedicated thread with its own asyncio event loop.
  The message handler fires in that thread's loop. We use call_soon_threadsafe
  to schedule the pipeline coroutine on Pulpo's event loop — no blocking, no
  shared state between the two loops.

Configuration (env vars):
  TELI_SESSIONS  comma-separated teli connection names to activate on startup
                 (e.g. "mybot,otherbot"). Defaults to all connections in teli's
                 data/connections.json if the teli library is importable.

Integration in main.py lifespan:
  import teli_poller
  # in startup:
  await teli_poller.start()
  # in shutdown:
  await teli_poller.stop()
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# L1 dedup — (session, chat_id, message_id).
# Telegram message_ids are unique per chat, so this is a tight key.
# Lost on restart (acceptable: same as wavi's L1).
_seen: set[tuple[str, str, int]] = set()

_started: set[str] = set()  # sessions currently wired


# ── Public interface ──────────────────────────────────────────────────────────


async def start() -> None:
    """Connect all configured teli sessions and wire them into the Pulpo pipeline."""
    sessions = _configured_sessions()
    if not sessions:
        logger.info("[teli-poll] no sessions configured (TELI_SESSIONS is empty)")
        return

    for session in sessions:
        try:
            await _start_session(session)
        except Exception:
            logger.exception("[teli-poll] failed to start session '%s'", session)

    logger.info("[teli-poll] started: %s", list(_started))


async def stop() -> None:
    """Stop all active teli sessions."""
    import tools.teli_driver as td

    for session in list(_started):
        try:
            await td.stop(session)
            _started.discard(session)
            logger.info("[teli-poll] session '%s' stopped", session)
        except Exception:
            logger.exception("[teli-poll] error stopping session '%s'", session)


# ── Session lifecycle ─────────────────────────────────────────────────────────


async def _start_session(session: str) -> None:
    import tools.teli_driver as td

    if session in _started:
        return

    result = await td.connect(session)
    if not result.get("ok"):
        logger.error(
            "[teli-poll] connect '%s' failed: %s",
            session, result.get("stderr", "unknown error"),
        )
        return

    pulpo_loop = asyncio.get_running_loop()
    td.add_handler(session, _make_handler(session, pulpo_loop))
    _started.add(session)
    logger.info("[teli-poll] session '%s' connected and wired", session)


def _make_handler(session: str, pulpo_loop: asyncio.AbstractEventLoop):
    """Return a teli-compatible async handler that bridges to Pulpo's event loop."""

    async def handle(msg: dict) -> None:
        # ── Filter ───────────────────────────────────────────────
        text = msg.get("text", "").strip()
        if not text:
            return  # non-text messages (photo, sticker…) — extend here later

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        message_id = int(msg.get("message_id", 0))

        # L1 dedup
        key = (session, chat_id, message_id)
        if key in _seen:
            return
        _seen.add(key)

        sender = msg.get("from", {})
        contact_name = (
            sender.get("username")
            or sender.get("first_name")
            or chat_id
        )

        # Bridge: schedule pipeline on Pulpo's event loop (non-blocking from bot's loop)
        pulpo_loop.call_soon_threadsafe(
            lambda: pulpo_loop.create_task(
                _pipeline(session, chat_id, contact_name, text)
            )
        )

    return handle


# ── Pipeline (runs on Pulpo's event loop) ────────────────────────────────────


async def _pipeline(
    session: str,
    contact_id: str,
    contact_name: str,
    text: str,
) -> None:
    import tools.teli_driver as td
    from config import get_bots_for_connection
    from db import log_message
    from graphs.compiler import run_flows
    from graphs.nodes.state import FlowState

    bot_ids = get_bots_for_connection(session)
    if not bot_ids:
        logger.debug("[teli-poll] no bot registered for session '%s'", session)
        return

    # Log inbound
    for bot_id in bot_ids:
        try:
            await log_message(bot_id, session, contact_id, contact_name, text)
        except Exception as e:
            logger.warning("[teli-poll] log_message error: %s", e)

    logger.info("[teli-poll] %s/%s → %r", session, contact_name, text[:80])

    state = FlowState(
        message=text,
        message_type="text",
        contact_phone=contact_id,
        contact_name=contact_name,
        canal="teli",
        connection_id=session,
    )
    try:
        state = await run_flows(state, connection_id=session)
    except Exception:
        logger.exception("[teli-poll] run_flows error for %s/%s", session, contact_id)
        return

    reply = state.reply or ""
    if not reply:
        return

    result = await td.send(session, contact_id, reply)
    if result.get("ok"):
        logger.info("[teli-poll] %s/%s ← reply sent (%d chars)", session, contact_name, len(reply))
        for bot_id in bot_ids:
            try:
                await log_message(bot_id, session, contact_id, "Bot", reply, outbound=True)
            except Exception as e:
                logger.warning("[teli-poll] log outbound error: %s", e)
    else:
        logger.warning(
            "[teli-poll] send failed for %s/%s: %s",
            session, contact_id, result.get("stderr", ""),
        )


# ── Config ────────────────────────────────────────────────────────────────────


def _configured_sessions() -> list[str]:
    """Return the list of teli session names to activate.

    Priority:
      1. TELI_SESSIONS env var (comma-separated)
      2. All connections in teli's data/connections.json (if importable)
    """
    env = os.getenv("TELI_SESSIONS", "").strip()
    if env:
        return [s.strip() for s in env.split(",") if s.strip()]

    try:
        from teli.connection import load_connections
        return [c["name"] for c in load_connections()]
    except Exception:
        return []
