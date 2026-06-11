"""
Async wrapper around the `wavi` CLI.
All calls use asyncio.create_subprocess_exec so they never block the event loop.

NOTE: wavi check-updates identifies contacts by display name only (no phone number).
As a result, contact_phone in FlowState holds the display name when coming from WhatsApp.
Filters and cooldowns key on display names, which works but differs from Telegram (numeric IDs).
"""
import asyncio
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

WAVI_BIN = "/Users/josetabuyo/.local/bin/wavi"
WAVI_ROOT = Path("/Users/josetabuyo/Development/wavi")
WAVI_SESSIONS_DIR = WAVI_ROOT / "data" / "sessions"
WAVI_QR_PAGE = WAVI_ROOT / "data" / "qr.html"


async def _run(*args: str, timeout: int = 120) -> tuple[int, str, str]:
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
        except Exception:
            pass
        return -1, "", "timeout"


async def connect(session: str = "default", new: bool = False) -> dict:
    args = ["connect", session]
    if new:
        args.append("--new")
    rc, out, err = await _run(*args, timeout=180)
    qr_page = str(WAVI_QR_PAGE) if WAVI_QR_PAGE.exists() else None
    ok = rc == 0 or "QR" in out or "authenticated" in out.lower()
    logger.info("[wavi] connect %s rc=%s", session, rc)
    return {"ok": ok, "stdout": out, "stderr": err, "qr_page": qr_page}


def daemon_running_by_pid(session: str) -> bool:
    """Fast check using the pid file — no subprocess spawn."""
    pid_file = WAVI_SESSIONS_DIR / session / "chrome_daemon.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # signal 0 = check if process exists, no actual signal sent
        return True
    except (ValueError, OSError):
        return False


async def status(session: str) -> dict:
    rc, out, err = await _run("status", session, timeout=15)
    daemon_running = "daemon=running" in out
    authenticated = "session=restored" in out
    return {
        "session": session,
        "daemon_running": daemon_running,
        "authenticated": authenticated,
        "raw": out,
    }


async def check_updates(session: str, reset: bool = False) -> dict:
    assets_dir = WAVI_ROOT / "output" / session / "last-updates"
    args = ["check-updates", session, "--assets", str(assets_dir)]
    if reset:
        args.append("--reset")
    rc, out, err = await _run(*args, timeout=60)
    updates_file = assets_dir / "updates.json"
    try:
        data = await asyncio.to_thread(_read_json, updates_file)
        return data
    except Exception as e:
        logger.warning("[wavi] check_updates %s: cannot read updates.json: %s", session, e)
        return {"status": "error", "new_inbound": []}


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def send(session: str, contact: str, message: str) -> dict:
    rc, out, err = await _run("send", session, contact, message, timeout=30)
    return {"ok": rc == 0, "stdout": out, "stderr": err}


async def stop(session: str) -> dict:
    rc, out, err = await _run("stop", session, timeout=30)
    return {"ok": rc == 0, "stdout": out}


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
    ]
