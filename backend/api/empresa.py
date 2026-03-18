"""Endpoints del portal de empresa — acceso con la contraseña del bot."""
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel

from config import load_config, save_config
from state import clients
import sim as sim_engine

router = APIRouter()


def _find_bot_by_password(config: dict, password: str):
    for bot in config.get("bots", []):
        if bot.get("password") == password:
            return bot
    return None


def _require_empresa(bot_id: str, x_empresa_pwd: str = Header(...)):
    config = load_config()
    bot = _find_bot_by_password(config, x_empresa_pwd)
    if not bot or bot["id"] != bot_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    return bot


# ─── Auth ────────────────────────────────────────────────────────

class EmpresaAuthBody(BaseModel):
    password: str


@router.post("/empresa/auth")
def empresa_auth(body: EmpresaAuthBody):
    config = load_config()
    bot = _find_bot_by_password(config, body.password)
    if not bot:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    return {"ok": True, "bot_id": bot["id"], "bot_name": bot["name"]}


# ─── Dashboard ───────────────────────────────────────────────────

@router.get("/empresa/{bot_id}")
def empresa_get(bot_id: str, x_empresa_pwd: str = Header(...)):
    bot = _require_empresa(bot_id, x_empresa_pwd)

    connections = []

    for phone in bot.get("phones", []):
        number = phone["number"]
        status = clients.get(number, {}).get("status", "stopped")
        connections.append({
            "id": number,
            "type": "whatsapp",
            "number": number,
            "status": status,
            "autoReplyMessage": phone.get("autoReplyMessage") or bot.get("autoReplyMessage", ""),
            "hasOwnMessage": "autoReplyMessage" in phone,
        })

    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        session_id = f"{bot['id']}-tg-{token_id}"
        status = clients.get(session_id, {}).get("status", "stopped")
        connections.append({
            "id": session_id,
            "type": "telegram",
            "number": session_id,
            "status": status,
            "autoReplyMessage": tg.get("autoReplyMessage") or bot.get("autoReplyMessage", ""),
            "hasOwnMessage": "autoReplyMessage" in tg,
        })

    return {
        "bot_id": bot["id"],
        "bot_name": bot["name"],
        "connections": connections,
        "autoReplyMessage": bot.get("autoReplyMessage", ""),
    }


# ─── Tools ───────────────────────────────────────────────────────

class EmpresaToolsBody(BaseModel):
    autoReplyMessage: str


@router.put("/empresa/{bot_id}/tools")
def empresa_put_tools(bot_id: str, body: EmpresaToolsBody, x_empresa_pwd: str = Header(...)):
    _require_empresa(bot_id, x_empresa_pwd)

    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    bot["autoReplyMessage"] = body.autoReplyMessage
    save_config(config)
    return {"ok": True}


# ─── Connect / QR / Disconnect ───────────────────────────────────

@router.post("/empresa/{bot_id}/connect/{number}")
async def empresa_connect(bot_id: str, number: str, background_tasks: BackgroundTasks, x_empresa_pwd: str = Header(...)):
    bot = _require_empresa(bot_id, x_empresa_pwd)

    if not any(p["number"] == number for p in bot.get("phones", [])):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    existing = clients.get(number, {})
    if existing.get("status") in ("connecting", "qr_needed", "qr_ready", "ready"):
        return {"ok": True, "status": existing["status"], "sessionId": number}

    if sim_engine.SIM_MODE:
        sim_engine.sim_connect(number, bot_id)
        return {"ok": True, "status": "ready", "sessionId": number}

    from api.whatsapp import _connect_and_get_qr
    background_tasks.add_task(_connect_and_get_qr, number, bot_id)
    return {"ok": True, "status": "connecting", "sessionId": number}


@router.get("/empresa/{bot_id}/qr/{session_id}")
def empresa_qr(bot_id: str, session_id: str, x_empresa_pwd: str = Header(...)):
    _require_empresa(bot_id, x_empresa_pwd)

    state = clients.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Sesión no iniciada")
    if state["status"] == "ready":
        return {"status": "ready"}
    if state.get("qr"):
        return {"status": state["status"], "qr": state["qr"]}
    return {"status": state["status"]}


@router.post("/empresa/{bot_id}/disconnect/{number}")
async def empresa_disconnect(bot_id: str, number: str, x_empresa_pwd: str = Header(...)):
    bot = _require_empresa(bot_id, x_empresa_pwd)

    if not any(p["number"] == number for p in bot.get("phones", [])):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    if sim_engine.SIM_MODE:
        sim_engine.sim_disconnect(number)
    else:
        from state import wa_session
        await wa_session.close_session(number)

    if number in clients:
        clients[number]["status"] = "disconnected"
        clients[number]["qr"] = None

    return {"ok": True}
