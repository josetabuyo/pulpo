"""
Endpoints de WhatsApp: connect, QR, refresh.
WhatsApp todavía corre en Node.js — estos endpoints son stubs que
serán implementados en Fase 4 cuando el adaptador Node.js haga POST aquí.
"""
from fastapi import APIRouter, HTTPException, Depends
from api.deps import require_admin, require_client
from config import load_config
from state import clients

router = APIRouter()


@router.post("/connect/{number}", dependencies=[Depends(require_client)])
def connect_phone(number: str):
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

    # WhatsApp aún no está implementado en Python — informar al cliente
    return {"ok": False, "status": "not_implemented", "sessionId": session_id,
            "detail": "WhatsApp todavía corre en Node.js (Fase 4)"}


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
