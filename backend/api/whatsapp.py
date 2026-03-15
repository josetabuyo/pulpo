"""
Endpoints de WhatsApp.

Flujo de "Vincular QR":
  1. POST /connect/{number}  → abre sesión, intenta restaurar auth
     - Si retorna status="restored": ya está listo, no hay QR
     - Si retorna status="connecting": hay que pedir QR y esperar scan
  2. GET  /qr/{session_id}   → devuelve el QR como base64 (polling)
  3. GET  /status/{session_id} → estado actual de la sesión
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from api.deps import require_admin, require_client
from config import load_config
from state import clients, wa_session

router = APIRouter()


@router.post("/connect/{number}", dependencies=[Depends(require_client)])
async def connect_phone(number: str, background_tasks: BackgroundTasks):
    config = load_config()
    found = None
    for bot in config.get("bots", []):
        if any(p["number"] == number for p in bot.get("phones", [])):
            found = {"bot_id": bot["id"], "number": number}
            break

    if not found:
        raise HTTPException(status_code=404, detail="Número no encontrado.")

    session_id = number
    existing = clients.get(session_id, {})

    # Si ya está conectado o en proceso, no relanzar
    if existing.get("status") in ("connecting", "qr_needed", "qr_ready", "ready"):
        return {"ok": True, "status": existing["status"], "sessionId": session_id}

    # Lanzar conexión en background (puede tardar varios segundos)
    background_tasks.add_task(_connect_and_get_qr, session_id, found["bot_id"])
    return {"ok": True, "status": "connecting", "sessionId": session_id}


@router.get("/qr/{session_id}", dependencies=[Depends(require_client)])
async def get_qr(session_id: str):
    state = clients.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Sesión no iniciada. Llamá primero a /connect.")
    if state["status"] == "ready":
        return {"status": "ready"}
    if state.get("qr"):
        return {"status": state["status"], "qr": state["qr"]}
    return {"status": state["status"]}


@router.get("/status/{session_id}", dependencies=[Depends(require_client)])
async def get_status(session_id: str):
    state = clients.get(session_id)
    if not state:
        return {"status": "unknown"}
    alive = await wa_session.is_page_alive(session_id)
    return {"status": state["status"], "alive": alive}


@router.post("/disconnect/{session_id}", dependencies=[Depends(require_admin)])
async def disconnect_session(session_id: str):
    """Cierra el contexto Chromium de una sesión WA limpiamente (sin kill)."""
    await wa_session.close_session(session_id)
    if session_id in clients:
        clients[session_id]["status"] = "disconnected"
        clients[session_id]["qr"] = None
    return {"ok": True, "session_id": session_id}


@router.post("/disconnect-all", dependencies=[Depends(require_admin)])
async def disconnect_all():
    """Cierra todos los contextos Chromium de la app sin tocar el browser del MCP."""
    closed = []
    for session_id, state in list(clients.items()):
        if state.get("type") != "whatsapp":
            continue
        await wa_session.close_session(session_id)
        clients[session_id]["status"] = "disconnected"
        clients[session_id]["qr"] = None
        closed.append(session_id)
    return {"ok": True, "closed": closed}


@router.post("/refresh", dependencies=[Depends(require_admin)])
async def refresh():
    reconnected = 0
    for session_id, state in clients.items():
        if state.get("type") != "whatsapp":
            continue
        if not await wa_session.is_page_alive(session_id):
            bot_id = state.get("bot_id", "")
            result = await wa_session.connect(session_id, bot_id)
            if result in ("restored", "qr_needed"):
                reconnected += 1
    return {"ok": True, "reconnected": reconnected}


# ------------------------------------------------------------------
# Tarea background: conectar y capturar QR si hace falta
# ------------------------------------------------------------------

def _get_wa_config(config: dict, number: str) -> dict:
    """Extrae allowedContacts y autoReplyMessage para un número dado."""
    for bot in config.get("bots", []):
        for phone_cfg in bot.get("phones", []):
            if phone_cfg.get("number") == number:
                return {
                    "bot_id": bot["id"],
                    "allowed_contacts": phone_cfg.get("allowedContacts", []),
                    "auto_reply": phone_cfg.get("autoReplyMessage") or bot.get("autoReplyMessage", ""),
                }
    return {"bot_id": "", "allowed_contacts": [], "auto_reply": ""}


async def _connect_and_get_qr(session_id: str, bot_id: str) -> None:
    result = await wa_session.connect(session_id, bot_id)

    if result == "restored":
        # Sesión restaurada — arrancar listener directamente
        cfg = _get_wa_config(load_config(), session_id)
        await wa_session.start_listening(
            session_id, cfg["bot_id"], session_id,
            cfg["allowed_contacts"], cfg["auto_reply"],
        )
        return

    if result == "qr_needed":
        qr = await wa_session.get_qr(session_id)
        if qr:
            authenticated = await wa_session.wait_for_auth(session_id)
            if authenticated:
                cfg = _get_wa_config(load_config(), session_id)
                await wa_session.start_listening(
                    session_id, cfg["bot_id"], session_id,
                    cfg["allowed_contacts"], cfg["auto_reply"],
                )
