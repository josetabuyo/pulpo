"""
Endpoints de WhatsApp: connect, QR, refresh.
Usa BrowserAutomation para abrir WhatsApp Web y capturar el QR.
"""
import asyncio
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from api.deps import require_admin, require_client
from config import load_config
from state import clients
from automation.browser import BrowserAutomation

router = APIRouter()
_automation = BrowserAutomation()


@router.post("/connect/{number}", dependencies=[Depends(require_client)])
async def connect_phone(number: str, background_tasks: BackgroundTasks):
    config = load_config()
    found = None
    for bot in config.get("bots", []):
        if any(p["number"] == number for p in bot.get("phones", [])):
            found = {"bot_id": bot["id"], "number": number, "session_id": number}
            break

    if not found:
        raise HTTPException(status_code=404, detail="Número no encontrado. Contactá al administrador.")

    session_id = found["session_id"]
    existing = clients.get(session_id, {})
    if existing.get("status") in ("connecting", "qr_ready", "authenticated", "ready"):
        return {"ok": True, "status": existing["status"], "sessionId": session_id}

    # Inicializar estado y lanzar automatización en background
    clients[session_id] = {
        "status": "connecting", "qr": None,
        "bot_id": found["bot_id"], "type": "whatsapp", "client": None,
    }
    background_tasks.add_task(_automation.whatsapp_get_qr, session_id)
    return {"ok": True, "status": "connecting", "sessionId": session_id}


@router.get("/qr/{session_id}", dependencies=[Depends(require_client)])
def get_qr(session_id: str):
    state = clients.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Sesión no iniciada")
    if state["status"] == "ready":
        return {"status": "ready"}
    if not state.get("qr"):
        return {"status": state["status"]}, 202
    return {"qr": state["qr"], "status": state["status"]}


@router.post("/refresh", dependencies=[Depends(require_admin)])
def refresh():
    # Stub: en Fase 4 esto pedirá al adaptador Node.js que reconecte clientes caídos
    return {"ok": True, "reconnected": 0}
