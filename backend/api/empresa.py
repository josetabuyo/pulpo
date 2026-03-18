"""Endpoints del portal de empresa — acceso con la contraseña del bot."""
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import text

from config import load_config, save_config
from state import clients
from db import AsyncSessionLocal, log_outbound_message
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


# ─── Mensajes / Chat ─────────────────────────────────────────────

def _owns_number(bot: dict, number: str) -> bool:
    return any(p["number"] == number for p in bot.get("phones", []))


@router.get("/empresa/{bot_id}/messages/{number}")
async def empresa_messages(bot_id: str, number: str, x_empresa_pwd: str = Header(...)):
    bot = _require_empresa(bot_id, x_empresa_pwd)
    if not _owns_number(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered "
                "FROM messages WHERE bot_phone = :number AND outbound = 0 "
                "ORDER BY timestamp DESC LIMIT 30"
            ),
            {"number": number},
        )
        rows = result.fetchall()

    seen = {}
    for r in rows:
        phone = r[1]
        if phone not in seen:
            seen[phone] = {"id": r[0], "phone": phone, "name": r[2], "body": r[3],
                           "timestamp": r[4], "answered": bool(r[5])}
    return list(seen.values())


@router.get("/empresa/{bot_id}/chat/{number}/{contact}")
async def empresa_chat_get(bot_id: str, number: str, contact: str, x_empresa_pwd: str = Header(...)):
    bot = _require_empresa(bot_id, x_empresa_pwd)
    if not _owns_number(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered, outbound "
                "FROM messages WHERE bot_phone = :number AND phone = :contact "
                "ORDER BY timestamp ASC LIMIT 100"
            ),
            {"number": number, "contact": contact},
        )
        rows = result.fetchall()

    return [{"id": r[0], "phone": r[1], "name": r[2], "body": r[3],
             "timestamp": r[4], "answered": bool(r[5]), "outbound": bool(r[6])}
            for r in rows]


class EmpresaSendBody(BaseModel):
    text: str


@router.post("/empresa/{bot_id}/chat/{number}/{contact}")
async def empresa_chat_send(bot_id: str, number: str, contact: str,
                            body: EmpresaSendBody, x_empresa_pwd: str = Header(...)):
    bot = _require_empresa(bot_id, x_empresa_pwd)
    if not _owns_number(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")

    if sim_engine.SIM_MODE:
        await log_outbound_message(bot_id, number, contact, body.text)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE messages SET answered = 1 WHERE bot_phone = :number AND phone = :contact AND answered = 0"),
                {"number": number, "contact": contact},
            )
            await session.commit()
        return {"ok": True}

    from state import wa_session
    ok = await wa_session.send_message(number, contact, body.text)
    if not ok:
        raise HTTPException(status_code=503, detail="No se pudo enviar. Verificá que el bot esté conectado.")

    await log_outbound_message(bot_id, number, contact, body.text)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE messages SET answered = 1 WHERE bot_phone = :number AND phone = :contact AND answered = 0"),
            {"number": number, "contact": contact},
        )
        await session.commit()
    return {"ok": True}
