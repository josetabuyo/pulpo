"""Endpoints del portal de bot — acceso con JWT Bearer token."""
import re
import logging
from fastapi import APIRouter, HTTPException, Depends, Request

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy import text

from pulpo.core.config import load_config, save_config
from pulpo.core.state import clients
from pulpo.core.db import AsyncSessionLocal, log_outbound_message
from pulpo.interfaces.ui.middleware import require_bot_auth, get_bot_id_from_token
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


def _require_bot(bot_id: str, token_bot_id: str = Depends(require_bot_auth)):
    """Verifica que el token JWT pertenezca al mismo bot_id del path."""
    if token_bot_id != bot_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta bot")
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrada")
    return bot


async def _require_bot_or_admin(bot_id: str, request: Request) -> dict:
    """
    Dependencia dual: acepta JWT Bearer (bot) o x-password admin.
    Permite que tanto el portal de bot como el dashboard admin
    accedan a los mismos endpoints.
    """
    import os
    admin_pwd = os.getenv("ADMIN_PASSWORD", "admin")

    # 1. Intentar JWT Bearer (bot)
    token_bot_id = get_bot_id_from_token(request)
    if token_bot_id is not None:
        if token_bot_id != bot_id:
            raise HTTPException(status_code=403, detail="No autorizado para esta bot")
        config = load_config()
        bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot no encontrada")
        return bot

    # 2. Fallback: x-password admin
    x_password = request.headers.get("x-password")
    if x_password and x_password == admin_pwd:
        config = load_config()
        bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot no encontrada")
        return bot

    raise HTTPException(status_code=401, detail="Token o contraseña requerida")


def _generate_bot_id(name: str, config: dict) -> str:
    existing = {b["id"] for b in config.get("bots", [])}
    base = re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_") or "bot"
    candidate = base
    i = 2
    while candidate in existing:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


# ─── Auth ────────────────────────────────────────────────────────

class BotAuthBody(BaseModel):
    password: str


@router.post("/bot/auth")
def bot_auth(body: BotAuthBody):
    config = load_config()
    bot = _find_bot_by_password(config, body.password)
    if not bot:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    return {"ok": True, "bot_id": bot["id"], "bot_name": bot["name"]}


# ─── Dashboard ───────────────────────────────────────────────────

@router.get("/bot/{bot_id}")
def bot_get(bot_id: str, bot: dict = Depends(_require_bot)):

    connections = []

    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        session_id = f"{bot['id']}-tg-{token_id}"
        status = clients.get(session_id, {}).get("status", "stopped")
        connections.append({
            "id": session_id,
            "type": "telegram",
            "number": session_id,
            "status": status,
        })

    return {
        "bot_id": bot["id"],
        "bot_name": bot["name"],
        "connections": connections,
    }


# ─── Mensajes / Chat ─────────────────────────────────────────────

def _owns_session(bot: dict, session_id: str) -> bool:
    if any(p["number"] == session_id for p in bot.get("phones", [])):
        return True
    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        if f"{bot['id']}-tg-{token_id}" == session_id:
            return True
    return False


@router.get("/bot/{bot_id}/messages/{number}")
async def bot_messages(bot_id: str, number: str, bot: dict = Depends(_require_bot)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta bot")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered "
                "FROM messages WHERE connection_phone = :number AND outbound = 0 "
                "AND id IN ("
                "  SELECT MAX(id) FROM messages "
                "  WHERE connection_phone = :number AND outbound = 0 "
                "  GROUP BY phone"
                ") ORDER BY timestamp DESC"
            ),
            {"number": _db_phone(number)},
        )
        rows = result.fetchall()

    return [
        {"id": r[0], "phone": r[1], "name": r[2], "body": r[3],
         "timestamp": r[4], "answered": bool(r[5])}
        for r in rows
    ]


@router.get("/bot/{bot_id}/history/{number}/{contact}")
async def bot_chat_get(bot_id: str, number: str, contact: str, bot: dict = Depends(_require_bot)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta bot")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered, outbound "
                "FROM messages WHERE connection_phone = :number AND phone = :contact "
                "ORDER BY timestamp ASC LIMIT 100"
            ),
            {"number": _db_phone(number), "contact": contact},
        )
        rows = result.fetchall()

    return [{"id": r[0], "phone": r[1], "name": r[2], "body": r[3],
             "timestamp": r[4], "answered": bool(r[5]), "outbound": bool(r[6])}
            for r in rows]


class BotSendBody(BaseModel):
    text: str


@router.post("/bot/{bot_id}/history/{number}/{contact}")
async def bot_chat_send(bot_id: str, number: str, contact: str,
                            body: BotSendBody, bot: dict = Depends(_require_bot)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta bot")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")

    db_number = _db_phone(number)

    def _accumulate_outbound(contact: str, msg_text: str) -> None:
        from pulpo.graphs.nodes.summarize import accumulate as _acc
        _acc(bot_id=bot_id, contact_phone=contact, contact_name=contact,
             msg_type="text", content=f"Tú: {msg_text}")

    if sim_engine.SIM_MODE:
        await log_outbound_message(bot_id, db_number, contact, body.text)
        _accumulate_outbound(contact, body.text)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE messages SET answered = 1 WHERE connection_phone = :number AND phone = :contact AND answered = 0"),
                {"number": db_number, "contact": contact},
            )
            await session.commit()
        return {"ok": True}

    tg_client = clients.get(number)
    if not tg_client:
        raise HTTPException(status_code=503, detail="Bot de Telegram no está activo")
    try:
        await tg_client["client"].bot.send_message(chat_id=int(contact), text=body.text)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No se pudo enviar por Telegram: {e}")

    await log_outbound_message(bot_id, db_number, contact, body.text)
    _accumulate_outbound(contact, body.text)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE messages SET answered = 1 WHERE connection_phone = :number AND phone = :contact AND answered = 0"),
            {"number": db_number, "contact": contact},
        )
        await session.commit()
    return {"ok": True}


# ─── Alta de bot (sin auth) ──────────────────────────────────

class NewBotBody(BaseModel):
    name: str
    password: str


@router.post("/bot/nueva")
def bot_new(body: NewBotBody):
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
        "phones": [],
        "telegram": [],
    }
    config["bots"].append(new_bot)
    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": new_bot["name"]}


# ─── Editar datos de la bot ──────────────────────────────────

class BotConfigBody(BaseModel):
    name: str | None = None
    password: str | None = None


@router.put("/bot/{bot_id}/config")
def bot_put_config(bot_id: str, body: BotConfigBody, _: dict = Depends(_require_bot)):

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

    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": bot["name"]}


# ─── Gestión de conexiones Telegram ──────────────────────────────

class AddTelegramBody(BaseModel):
    token: str


@router.post("/bot/{bot_id}/telegram")
async def bot_add_telegram(bot_id: str, body: AddTelegramBody, _: dict = Depends(_require_bot)):
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
            from pulpo.bots.telegram_bot import build_telegram_app
            cfg = {"connection_id": bot_id, "token": token}
            tg_app = build_telegram_app(cfg)
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling(drop_pending_updates=True)
            clients[session_id] = {"status": "ready", "qr": None, "connection_id": bot_id, "type": "telegram", "client": tg_app}
        except Exception:
            requires_restart = True

    return {"ok": True, "session_id": session_id, "requires_restart": requires_restart}


@router.delete("/bot/{bot_id}/telegram/{token_id}")
def bot_remove_telegram(bot_id: str, token_id: str, _: dict = Depends(_require_bot)):

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


@router.put("/bot/{bot_id}/paused")
async def set_bot_paused(
    bot_id: str,
    body: dict,
    _: dict = Depends(_require_bot_or_admin),
):
    """
    Pausa o reanuda el bot de una bot.
    body: { "paused": true | false }
    Bot pausado = conexión viva pero sin replies automáticos.
    Acepta tanto JWT Bearer (bot) como x-password (admin).
    """
    import paused as _paused_mod
    should_pause = bool(body.get("paused", False))
    if should_pause:
        _paused_mod.pause(bot_id)
    else:
        _paused_mod.resume(bot_id)
    return {"ok": True, "paused": should_pause, "bot_id": bot_id}


@router.get("/bot/{bot_id}/paused")
async def get_bot_paused(
    bot_id: str,
    _: dict = Depends(_require_bot_or_admin),
):
    import paused as _paused_mod
    return {"paused": _paused_mod.is_paused(bot_id), "bot_id": bot_id}
