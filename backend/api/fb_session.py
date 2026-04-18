"""
Endpoint para renovar la sesión de Facebook (cookies) desde el dashboard.

POST /api/fb/refresh-session?page_id=luganense
  — Inicia el login en background (abre browser visible en el servidor).
  — Solo admin.

GET /api/fb/session-status?page_id=luganense
  — Estado del último intento de login.
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, Query
from api.deps import require_admin

router = APIRouter()
logger = logging.getLogger(__name__)

# Estado global del último refresh (uno a la vez)
_status: dict = {"state": "idle", "page_id": "", "message": "Listo"}


@router.post("/fb/refresh-session", dependencies=[Depends(require_admin)])
async def refresh_session(page_id: str = Query("luganense")):
    """Inicia renovación de cookies FB en background. Abre browser visible en el servidor."""
    global _status

    if _status["state"] == "running":
        return {"ok": False, "message": f"Ya hay un login en curso para '{_status['page_id']}'"}

    _status = {"state": "running", "page_id": page_id, "message": "Abriendo browser…"}
    logger.info("[fb_session] Iniciando refresh de sesión para '%s'", page_id)

    asyncio.get_event_loop().create_task(_do_refresh(page_id))
    return {"ok": True, "message": "Browser abierto — completá el login en el servidor"}


@router.get("/fb/session-status", dependencies=[Depends(require_admin)])
async def session_status(page_id: str = Query("luganense")):
    """Retorna el estado del último intento de login."""
    if _status["page_id"] and _status["page_id"] != page_id:
        return {"state": "idle", "page_id": page_id, "message": "Sin actividad reciente"}
    return _status


async def _do_refresh(page_id: str):
    global _status
    try:
        from nodes.fetch_facebook import _do_login_visible, _SESSIONS_DIR
        cookies_path = _SESSIONS_DIR / f"fb-{page_id}" / "cookies.json"
        cookies_path.parent.mkdir(parents=True, exist_ok=True)

        import os
        email    = os.getenv("FB_EMAIL", "").strip()
        password = os.getenv("FB_PASSWORD", "").strip()

        if not email or not password:
            _status = {"state": "error", "page_id": page_id, "message": "FB_EMAIL / FB_PASSWORD no configurados"}
            return

        ok = await _do_login_visible(email, password, cookies_path)

        if ok:
            # Invalidar caché para que el próximo fetch use las cookies nuevas
            from nodes import fetch_facebook
            fetch_facebook.invalidate(page_id)
            _status = {"state": "ok", "page_id": page_id, "message": "Sesión renovada correctamente ✓"}
            logger.info("[fb_session] Sesión renovada para '%s'", page_id)
        else:
            _status = {"state": "error", "page_id": page_id, "message": "Login fallido — revisá el browser"}

    except Exception as e:
        logger.error("[fb_session] Error en refresh: %s", e)
        _status = {"state": "error", "page_id": page_id, "message": f"Error: {e}"}
