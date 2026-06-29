"""
Business logic for Wavi (WhatsApp via external daemon) session management.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

import asyncio
import os
import re
import sys
from pathlib import Path

import pulpo.tools.wavi_driver as wd

_BACKEND = str(Path(__file__).parent.parent.parent.parent / "backend")


from pulpo.core.state import wavi_status


def _wavi_poller():
    if _BACKEND not in sys.path:
        sys.path.insert(0, _BACKEND)
    import wavi_poller as _wp
    return _wp

_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# Tracks sessions currently in the middle of a connect attempt.
_CONNECTING_SESSIONS: set[str] = set()


def validate_session_name(session: str) -> str:
    """
    Validates a session name against the allowed pattern.
    Raises ValueError on invalid names.
    Returns the session name unchanged if valid.
    """
    if not _SESSION_RE.match(session or ""):
        raise ValueError(
            "Nombre de sesión inválido: solo letras, números, '-' y '_' (máx. 64)."
        )
    return session


async def create_wavi_session(session: str) -> dict:
    """
    Creates (or re-connects) a Wavi session and starts the connection background task.
    Returns {ok, qr_url, status, session}.
    """
    session = validate_session_name(session or "default")
    wavi_status[session] = "connecting"
    if session not in _CONNECTING_SESSIONS:
        _CONNECTING_SESSIONS.add(session)
        asyncio.create_task(_connect_and_cleanup(session))
    return {"ok": True, "qr_url": "/api/wavi/qr-page", "status": "connecting", "session": session}


async def _connect_and_cleanup(session: str) -> None:
    try:
        result = await wd.connect(session, new=True)
        wavi_status[session] = "ready" if result.get("ok") else "disconnected"
    except Exception:
        wavi_status[session] = "disconnected"
    finally:
        _CONNECTING_SESSIONS.discard(session)


async def reconnect_wavi_session(session: str) -> dict:
    """
    Reconnects an existing Wavi session (or creates a new one if no profile exists).
    Returns {ok, qr_url, status, session}.
    """
    session = validate_session_name(session)
    _wavi_poller().resume_session(session)
    wavi_status[session] = "connecting"
    if session not in _CONNECTING_SESSIONS:
        _CONNECTING_SESSIONS.add(session)
        profile_path = wd.WAVI_SESSIONS_DIR / session
        is_new = not profile_path.exists()
        asyncio.create_task(_reconnect_and_cleanup(session, is_new))
    return {"ok": True, "qr_url": "/api/wavi/qr-page", "status": "connecting", "session": session}


async def _reconnect_and_cleanup(session: str, is_new: bool = False) -> None:
    try:
        result = await wd.connect(session, new=is_new)
        wavi_status[session] = "ready" if result.get("ok") else "disconnected"
    except Exception:
        wavi_status[session] = "disconnected"
    finally:
        _CONNECTING_SESSIONS.discard(session)


async def list_wavi_sessions() -> list[dict]:
    """
    Returns all known Wavi sessions with their daemon/auth status.
    Sessions currently connecting are included even if not yet on disk.
    """
    names = wd.list_session_names()
    statuses = await asyncio.gather(*(wd.status(name) for name in names))
    results = []
    for name, st in zip(names, statuses):
        results.append({
            "session": name,
            "daemon_running": st["daemon_running"],
            "authenticated": st["authenticated"],
            "connecting": name in _CONNECTING_SESSIONS,
        })
    for name in _CONNECTING_SESSIONS:
        if name not in names:
            results.append({
                "session": name,
                "daemon_running": False,
                "authenticated": False,
                "connecting": True,
            })
    return results


async def get_wavi_session(session: str) -> dict:
    """Returns the status dict for a single Wavi session."""
    validate_session_name(session)
    st = await wd.status(session)
    st["connecting"] = session in _CONNECTING_SESSIONS
    return st


async def stop_wavi_session(session: str) -> dict:
    """Stops a Wavi session and marks it as stopped. Returns the stop result dict."""
    validate_session_name(session)
    result = await wd.stop(session)
    wavi_status[session] = "stopped"
    return result


def get_boarding_path(session: str) -> str:
    """Returns the filesystem path to the QR boarding page for a session."""
    validate_session_name(session)
    return str(wd.get_qr_page_path())


def get_qr_page_html() -> str:
    """
    Returns the HTML content of the QR page, or a placeholder if not yet generated.
    """
    qr_path = wd.get_qr_page_path()
    if not qr_path.exists():
        return (
            "<html><body style='font-family:sans-serif;padding:20px'>"
            "<p>QR aún no generado — esperá unos segundos y recargá esta página.</p>"
            "</body></html>"
        )
    return qr_path.read_text(encoding="utf-8")
