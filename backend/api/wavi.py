import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.deps import require_admin, ADMIN_PASSWORD
import tools.wavi_driver as wd

router = APIRouter()

_CONNECTING_SESSIONS: set[str] = set()

# Los nombres de sesión terminan en rutas (data/sessions/{session}) y en argv
# del CLI wavi — un nombre arbitrario podría escapar del directorio.
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _validate_session(session: str) -> str:
    if not _SESSION_RE.match(session or ""):
        raise HTTPException(
            status_code=422,
            detail="Nombre de sesión inválido: solo letras, números, '-' y '_' (máx. 64).",
        )
    return session


class SessionCreate(BaseModel):
    session: str | None = None


@router.post("/wavi/sessions", dependencies=[Depends(require_admin)])
async def create_wavi_session(body: SessionCreate):
    session = _validate_session(body.session or "default")
    if session not in _CONNECTING_SESSIONS:
        _CONNECTING_SESSIONS.add(session)
        asyncio.create_task(_connect_and_cleanup(session))
    return {"ok": True, "qr_url": "/api/wavi/qr-page", "status": "connecting", "session": session}


async def _connect_and_cleanup(session: str):
    try:
        await wd.connect(session, new=True)
    finally:
        _CONNECTING_SESSIONS.discard(session)


@router.get("/wavi/sessions", dependencies=[Depends(require_admin)])
async def list_wavi_sessions():
    names = wd.list_session_names()
    # El status de cada sesión invoca el CLI wavi (lento) — en paralelo
    statuses = await asyncio.gather(*(wd.status(name) for name in names))
    results = []
    for name, st in zip(names, statuses):
        results.append({
            "session": name,
            "daemon_running": st["daemon_running"],
            "authenticated": st["authenticated"],
            "connecting": name in _CONNECTING_SESSIONS,
        })
    # Also show sessions currently connecting that aren't yet in sessions dir
    for name in _CONNECTING_SESSIONS:
        if name not in names:
            results.append({"session": name, "daemon_running": False, "authenticated": False, "connecting": True})
    return results


@router.get("/wavi/sessions/{session}", dependencies=[Depends(require_admin)])
async def get_wavi_session(session: str):
    _validate_session(session)
    st = await wd.status(session)
    st["connecting"] = session in _CONNECTING_SESSIONS
    return st


@router.delete("/wavi/sessions/{session}", dependencies=[Depends(require_admin)])
async def stop_wavi_session(session: str):
    _validate_session(session)
    result = await wd.stop(session)
    return result


@router.get("/wavi/sessions/{session}/boarding", dependencies=[Depends(require_admin)])
def get_boarding(session: str):
    _validate_session(session)
    return {"path": str(wd.get_qr_page_path())}


@router.get("/wavi/qr-page")
def get_qr_page(pwd: str = Query(default="")):
    if pwd != ADMIN_PASSWORD:
        return HTMLResponse("<h1>401 No autorizado</h1>", status_code=401)
    qr_path = wd.get_qr_page_path()
    if not qr_path.exists():
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:20px'>"
            "<p>QR aún no generado — esperá unos segundos y recargá esta página.</p>"
            "</body></html>"
        )
    return HTMLResponse(qr_path.read_text(encoding="utf-8"))
