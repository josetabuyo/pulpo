"""Endpoints del portal de empresa — acceso con la contraseña del bot."""
import re
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import text

from config import load_config, save_config
from state import clients
from db import AsyncSessionLocal, log_outbound_message
import sim as sim_engine

router = APIRouter()


def _db_phone(number: str) -> str:
    """Telegram sessions usan session_id como key en clients pero guardan en DB solo el token_id."""
    # Formato: "{bot_id}-tg-{token_id}" → devuelve "{token_id}"
    if "-tg-" in number:
        return number.split("-tg-")[-1]
    return number


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


def _generate_bot_id(name: str, config: dict) -> str:
    existing = {b["id"] for b in config.get("bots", [])}
    base = re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_") or "empresa"
    candidate = base
    i = 2
    while candidate in existing:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


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

def _owns_session(bot: dict, session_id: str) -> bool:
    if any(p["number"] == session_id for p in bot.get("phones", [])):
        return True
    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        if f"{bot['id']}-tg-{token_id}" == session_id:
            return True
    return False


@router.get("/empresa/{bot_id}/messages/{number}")
async def empresa_messages(bot_id: str, number: str, x_empresa_pwd: str = Header(...)):
    bot = _require_empresa(bot_id, x_empresa_pwd)
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered "
                "FROM messages WHERE bot_phone = :number AND outbound = 0 "
                "ORDER BY timestamp DESC LIMIT 30"
            ),
            {"number": _db_phone(number)},
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
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered, outbound "
                "FROM messages WHERE bot_phone = :number AND phone = :contact "
                "ORDER BY timestamp ASC LIMIT 100"
            ),
            {"number": _db_phone(number), "contact": contact},
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
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")

    db_number = _db_phone(number)

    if sim_engine.SIM_MODE:
        await log_outbound_message(bot_id, db_number, contact, body.text)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE messages SET answered = 1 WHERE bot_phone = :number AND phone = :contact AND answered = 0"),
                {"number": db_number, "contact": contact},
            )
            await session.commit()
        return {"ok": True}

    if "-tg-" in number:
        tg_client = clients.get(number)
        if not tg_client:
            raise HTTPException(status_code=503, detail="Bot de Telegram no está activo")
        try:
            await tg_client["client"].bot.send_message(chat_id=int(contact), text=body.text)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"No se pudo enviar por Telegram: {e}")
    else:
        from state import wa_session
        ok = await wa_session.send_message(number, contact, body.text)
        if not ok:
            raise HTTPException(status_code=503, detail="No se pudo enviar. Verificá que el bot esté conectado.")

    await log_outbound_message(bot_id, db_number, contact, body.text)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE messages SET answered = 1 WHERE bot_phone = :number AND phone = :contact AND answered = 0"),
            {"number": db_number, "contact": contact},
        )
        await session.commit()
    return {"ok": True}

# ─── Alta de empresa (sin auth) ──────────────────────────────────

class NuevaEmpresaBody(BaseModel):
    name: str
    password: str
    autoReplyMessage: str = ""


@router.post("/empresa/nueva")
def empresa_nueva(body: NuevaEmpresaBody):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="El nombre es requerido")
    if not body.password.strip():
        raise HTTPException(status_code=400, detail="La contraseña es requerida")

    config = load_config()
    if _find_bot_by_password(config, body.password):
        raise HTTPException(status_code=409, detail="Esa contraseña ya está en uso")

    bot_id = _generate_bot_id(body.name, config)
    new_bot = {
        "id": bot_id,
        "name": body.name.strip(),
        "password": body.password,
        "autoReplyMessage": body.autoReplyMessage,
        "phones": [],
        "telegram": [],
    }
    config["bots"].append(new_bot)
    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": new_bot["name"]}


# ─── Editar datos de la empresa ──────────────────────────────────

class EmpresaConfigBody(BaseModel):
    name: str | None = None
    password: str | None = None
    autoReplyMessage: str | None = None


@router.put("/empresa/{bot_id}/config")
def empresa_put_config(bot_id: str, body: EmpresaConfigBody, x_empresa_pwd: str = Header(...)):
    _require_empresa(bot_id, x_empresa_pwd)

    config = load_config()
    bot = next((b for b in config["bots"] if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="Nombre no puede ser vacío")
        bot["name"] = body.name.strip()

    if body.password is not None:
        if not body.password.strip():
            raise HTTPException(status_code=400, detail="Contraseña no puede ser vacía")
        for b in config["bots"]:
            if b["id"] != bot_id and b.get("password") == body.password:
                raise HTTPException(status_code=409, detail="Esa contraseña ya está en uso")
        bot["password"] = body.password

    if body.autoReplyMessage is not None:
        bot["autoReplyMessage"] = body.autoReplyMessage

    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": bot["name"]}


# ─── Gestión de conexiones WhatsApp ──────────────────────────────

class AddWhatsappBody(BaseModel):
    number: str


@router.post("/empresa/{bot_id}/whatsapp")
def empresa_add_whatsapp(bot_id: str, body: AddWhatsappBody, x_empresa_pwd: str = Header(...)):
    _require_empresa(bot_id, x_empresa_pwd)
    number = body.number.strip()
    if not number:
        raise HTTPException(status_code=400, detail="Número requerido")

    config = load_config()
    for b in config["bots"]:
        if any(p["number"] == number for p in b.get("phones", [])):
            raise HTTPException(status_code=409, detail=f"El número {number} ya está configurado")

    bot = next(b for b in config["bots"] if b["id"] == bot_id)
    bot.setdefault("phones", []).append({"number": number})
    save_config(config)

    if sim_engine.SIM_MODE:
        sim_engine.sim_connect(number, bot_id)

    return {"ok": True, "number": number}


@router.delete("/empresa/{bot_id}/whatsapp/{number}")
async def empresa_remove_whatsapp(bot_id: str, number: str, x_empresa_pwd: str = Header(...)):
    _require_empresa(bot_id, x_empresa_pwd)

    config = load_config()
    bot = next((b for b in config["bots"] if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    original = len(bot.get("phones", []))
    bot["phones"] = [p for p in bot.get("phones", []) if p["number"] != number]
    if len(bot["phones"]) == original:
        raise HTTPException(status_code=404, detail="Número no encontrado")

    save_config(config)

    if sim_engine.SIM_MODE:
        sim_engine.sim_disconnect(number)
    else:
        from state import wa_session
        await wa_session.close_session(number)

    clients.pop(number, None)
    return {"ok": True}


# ─── Gestión de conexiones Telegram ──────────────────────────────

class AddTelegramBody(BaseModel):
    token: str


@router.post("/empresa/{bot_id}/telegram")
async def empresa_add_telegram(bot_id: str, body: AddTelegramBody, x_empresa_pwd: str = Header(...)):
    _require_empresa(bot_id, x_empresa_pwd)
    token = body.token.strip()
    if not token or ":" not in token:
        raise HTTPException(status_code=400, detail="Token inválido (formato: 123456789:ABC...)")

    token_id = token.split(":")[0]
    session_id = f"{bot_id}-tg-{token_id}"

    config = load_config()
    for b in config["bots"]:
        for tg in b.get("telegram", []):
            if tg["token"].split(":")[0] == token_id:
                raise HTTPException(status_code=409, detail="Ese token ya está configurado")

    bot = next(b for b in config["bots"] if b["id"] == bot_id)
    bot.setdefault("telegram", []).append({"token": token})
    save_config(config)

    requires_restart = False
    if sim_engine.SIM_MODE:
        sim_engine.sim_connect(session_id, bot_id)
    else:
        # Intentar iniciar dinámicamente
        try:
            from bots.telegram_bot import build_telegram_app
            from main import _tg_apps
            cfg = {"bot_id": bot_id, "token": token, "allowed_contacts": [], "reply_message": bot.get("autoReplyMessage", "")}
            tg_app = build_telegram_app(cfg)
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling(drop_pending_updates=True)
            _tg_apps.append(tg_app)
            clients[session_id] = {"status": "ready", "qr": None, "bot_id": bot_id, "type": "telegram", "client": tg_app}
        except Exception:
            requires_restart = True

    return {"ok": True, "session_id": session_id, "requires_restart": requires_restart}


@router.delete("/empresa/{bot_id}/telegram/{token_id}")
def empresa_remove_telegram(bot_id: str, token_id: str, x_empresa_pwd: str = Header(...)):
    _require_empresa(bot_id, x_empresa_pwd)

    config = load_config()
    bot = next((b for b in config["bots"] if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    original = len(bot.get("telegram", []))
    bot["telegram"] = [tg for tg in bot.get("telegram", []) if tg["token"].split(":")[0] != token_id]
    if len(bot["telegram"]) == original:
        raise HTTPException(status_code=404, detail="Token no encontrado")

    save_config(config)
    session_id = f"{bot_id}-tg-{token_id}"
    if sim_engine.SIM_MODE:
        sim_engine.sim_disconnect(session_id)
    clients.pop(session_id, None)
    return {"ok": True}
