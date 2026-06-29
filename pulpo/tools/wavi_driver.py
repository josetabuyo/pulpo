"""
Wrapper around the wavi Python library.

Replaces the previous subprocess-based driver. Same public interface —
wavi_poller.py and api/wavi.py require no changes.

connect() is the only function that still uses subprocess: it's a one-time
interactive operation (starts Chrome + QR scan) and the library has no
headless equivalent for the daemon-start flow.
"""
import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

WAVI_BIN = os.getenv("WAVI_BIN", str(Path.home() / ".local" / "bin" / "wavi"))
WAVI_ROOT = Path(os.getenv("WAVI_ROOT", str(Path.home() / "Development" / "wavi")))
WAVI_SESSIONS_DIR = Path(os.getenv(
    "WAVI_SESSIONS_DIR",
    str(WAVI_ROOT / "data" / "sessions"),
))
WAVI_QR_PAGE = WAVI_ROOT / "data" / "qr.html"


def _profile(session: str) -> Path:
    """Resolve session name or alias to profile path via aliases.json (wavi convention)."""
    import json
    aliases_file = WAVI_SESSIONS_DIR / "aliases.json"
    if aliases_file.exists():
        aliases = json.loads(aliases_file.read_text())
        if session in aliases:
            return WAVI_SESSIONS_DIR / aliases[session]
    return WAVI_SESSIONS_DIR / session


# ── connect — stays as subprocess (interactive QR flow) ──────────────────────

async def _run_subprocess(*args: str, timeout: int = 120) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        WAVI_BIN, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return -1, "", "timeout"


async def connect(session: str = "default", new: bool = False) -> dict:
    """Start Chrome daemon and authenticate (QR scan if needed). Interactive — uses subprocess."""
    args = ["connect", session]
    if new:
        args.append("--new")
    rc, out, err = await _run_subprocess(*args, timeout=180)
    qr_page = str(WAVI_QR_PAGE) if WAVI_QR_PAGE.exists() else None
    ok = rc == 0 or "QR" in out or "authenticated" in out.lower()
    logger.info("[wavi] connect %s rc=%s", session, rc)
    return {"ok": ok, "stdout": out, "stderr": err, "qr_page": qr_page}


# ── direct library calls ──────────────────────────────────────────────────────

def daemon_running_by_pid(session: str) -> bool:
    """Fast check using the pid file — no subprocess, no library overhead."""
    from wavi.session import WASession
    return WASession(_profile(session)).daemon_alive()


async def status(session: str) -> dict:
    from wavi.session import WASession, _is_process_alive
    profile = _profile(session)
    s = WASession(profile)
    pid = s._load_pid()
    daemon_running = bool(pid and _is_process_alive(pid))
    if not daemon_running:
        return {"session": session, "daemon_running": False, "authenticated": False, "raw": ""}
    try:
        result = await s.connect()
        await s.close()
        return {
            "session": session,
            "daemon_running": True,
            "authenticated": result == "restored",
            "raw": result,
        }
    except Exception as e:
        logger.warning("[wavi] status %s error: %s", session, e)
        return {"session": session, "daemon_running": True, "authenticated": False, "raw": str(e)}


async def check_updates(session: str, reset: bool = False) -> dict:
    from wavi.runner import WARunner
    profile = _profile(session)
    assets_dir = WAVI_ROOT / "output" / session / "last-updates"
    runner = WARunner(profile)
    try:
        return await runner.check_updates(assets_dir=assets_dir, reset=reset)
    except Exception as e:
        logger.warning("[wavi] check_updates %s error: %s", session, e)
        return {"status": "error", "error": str(e), "new_inbound": []}


async def get_last_inbound(session: str, contact: str) -> str | None:
    """
    Fetch the last full inbound text message from a contact via wavi get --newest.
    Returns the message text, or None if unavailable.
    """
    from wavi.runner import run_enhanced
    contact_slug = contact.lower().replace(" ", "_")
    assets_dir = WAVI_ROOT / "output" / session / contact_slug
    try:
        result = await run_enhanced(
            profile_dir=_profile(session),
            contact=contact,
            assets_dir=assets_dir,
            max_iterations=1,
            newest=True,
        )
        for b in result["bubbles"]:
            if b.sender == "other" and b.msg_type == "text" and b.text.strip():
                return b.text.strip()
        return None
    except Exception as e:
        logger.warning("[wavi] get_last_inbound %s/%s error: %s", session, contact, e)
        return None


async def send(session: str, contact: str, message: str) -> dict:
    from wavi.session import WASession
    profile = _profile(session)
    s = WASession(profile)
    try:
        st = await s.connect()
        if st != "restored":
            return {"ok": False, "stdout": "", "stderr": f"session not authenticated: {st}"}
        await s.navigate_to_contact(contact)
        await s.send_message(message)
        return {"ok": True, "stdout": "", "stderr": ""}
    except Exception as e:
        logger.warning("[wavi] send %s/%s error: %s", session, contact, e)
        return {"ok": False, "stdout": "", "stderr": str(e)}
    finally:
        try:
            await s.close()
        except Exception:
            pass


async def stop(session: str) -> dict:
    from wavi.session import WASession
    profile = _profile(session)
    s = WASession(profile)
    try:
        await s.stop_daemon()
        return {"ok": True, "stdout": "Daemon stopped."}
    except Exception as e:
        logger.warning("[wavi] stop %s error: %s", session, e)
        return {"ok": False, "stdout": str(e)}


def get_qr_page_path() -> Path:
    return WAVI_QR_PAGE


def list_session_names() -> list[str]:
    if not WAVI_SESSIONS_DIR.exists():
        return []
    return [
        d.name for d in WAVI_SESSIONS_DIR.iterdir()
        if d.is_dir()
        and not d.name.startswith("_tmp_")
        and not d.name.startswith("_new_")
        and not d.name.startswith(".")
        and not d.name.endswith("_bak")
    ]
