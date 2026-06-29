"""
Router: /wavi

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

The /qr-page endpoint serves raw HTML for a browser (kept auth-free here;
the parent mount protects it via auth middleware).

Route layout (parent mounts at /wavi):
  POST /sessions
  POST /sessions/{session}/connect
  GET  /sessions
  GET  /sessions/{session}
  DELETE /sessions/{session}
  GET  /sessions/{session}/boarding
  GET  /qr-page
"""
import asyncio
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from pulpo.business import wavi as wavi_svc

router = APIRouter()

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


@router.post("/sessions")
async def create_wavi_session(body: SessionCreate):
    session = _validate_session(body.session or "default")
    try:
        return await wavi_svc.create_session(session=session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session}/connect")
async def reconnect_wavi_session(session: str):
    session = _validate_session(session)
    try:
        return await wavi_svc.reconnect_session(session=session)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions")
async def list_wavi_sessions():
    try:
        return await wavi_svc.list_sessions()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions/{session}")
async def get_wavi_session(session: str):
    _validate_session(session)
    try:
        return await wavi_svc.get_session(session=session)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/sessions/{session}")
async def stop_wavi_session(session: str):
    _validate_session(session)
    try:
        return await wavi_svc.stop_session(session=session)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions/{session}/boarding")
def get_boarding(session: str):
    _validate_session(session)
    try:
        return wavi_svc.get_boarding(session=session)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/qr-page")
def get_qr_page():
    """
    Sirve la página HTML del QR de WhatsApp Web.
    La autenticación es responsabilidad del padre (interfaces/ui/app.py).
    """
    try:
        content = wavi_svc.get_qr_page_html()
    except FileNotFoundError:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:20px'>"
            "<p>QR aún no generado — esperá unos segundos y recargá esta página.</p>"
            "</body></html>"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return HTMLResponse(content)
