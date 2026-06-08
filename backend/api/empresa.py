"""Endpoints del portal de empresa — acceso con JWT Bearer token."""
import re
import logging
from fastapi import APIRouter, HTTPException, Depends, Request

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy import text

from config import load_config, save_config
from state import clients
from db import AsyncSessionLocal, log_outbound_message
from middleware_auth import require_empresa_auth
import sim as sim_engine

router = APIRouter()


def _db_phone(number: str) -> str:
    """Telegram sessions usan session_id como key en clients pero guardan en DB solo el token_id."""
    # Formato: "{bot_id}-tg-{token_id}" → devuelve "{token_id}"
    if "-tg-" in number:
        return number.split("-tg-")[-1]
    return number


def _find_bot_by_password(config: dict, password: str):
    for bot in config.get("empresas", []):
        if bot.get("password") == password:
            return bot
    return None


def _require_empresa(bot_id: str, token_bot_id: str = Depends(require_empresa_auth)):
    """Verifica que el token JWT pertenezca al mismo bot_id del path."""
    if token_bot_id != bot_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
    config = load_config()
    bot = next((b for b in config.get("empresas", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return bot


async def _require_empresa_or_admin(bot_id: str, request: Request) -> dict:
    """
    Dependencia dual: acepta JWT Bearer (empresa) o x-password admin.
    Permite que tanto el portal de empresa como el dashboard admin
    accedan a los mismos endpoints.
    """
    import os
    from middleware_auth import get_empresa_id_from_token

    # 1. Intentar JWT Bearer (empresa)
    empresa_id = get_empresa_id_from_token(request)
    if empresa_id is not None:
        if empresa_id != bot_id:
            raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
        config = load_config()
        bot = next((b for b in config.get("empresas", []) if b["id"] == bot_id), None)
        if not bot:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        return bot

    # 2. Fallback: x-password admin
    admin_pwd = os.getenv("ADMIN_PASSWORD", "admin")
    x_password = request.headers.get("x-password")
    if x_password and x_password == admin_pwd:
        config = load_config()
        bot = next((b for b in config.get("empresas", []) if b["id"] == bot_id), None)
        if not bot:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        return bot

    raise HTTPException(status_code=401, detail="Token o contraseña requerida")


def _generate_bot_id(name: str, config: dict) -> str:
    existing = {b["id"] for b in config.get("empresas", [])}
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
def empresa_get(bot_id: str, bot: dict = Depends(_require_empresa)):

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


@router.get("/empresa/{bot_id}/messages/{number}")
async def empresa_messages(bot_id: str, number: str, bot: dict = Depends(_require_empresa)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

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


@router.get("/empresa/{bot_id}/chat/{number}/{contact}")
async def empresa_chat_get(bot_id: str, number: str, contact: str, bot: dict = Depends(_require_empresa)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

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


class EmpresaSendBody(BaseModel):
    text: str


@router.post("/empresa/{bot_id}/chat/{number}/{contact}")
async def empresa_chat_send(bot_id: str, number: str, contact: str,
                            body: EmpresaSendBody, bot: dict = Depends(_require_empresa)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")

    db_number = _db_phone(number)

    def _accumulate_outbound(contact: str, msg_text: str) -> None:
        from graphs.nodes.summarize import accumulate as _acc
        _acc(empresa_id=bot_id, contact_phone=contact, contact_name=contact,
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

# ─── Alta de empresa (sin auth) ──────────────────────────────────

class NuevaEmpresaBody(BaseModel):
    name: str
    password: str


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
        "phones": [],
        "telegram": [],
    }
    config["empresas"].append(new_bot)
    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": new_bot["name"]}


# ─── Editar datos de la empresa ──────────────────────────────────

class EmpresaConfigBody(BaseModel):
    name: str | None = None
    password: str | None = None


@router.put("/empresa/{bot_id}/config")
def empresa_put_config(bot_id: str, body: EmpresaConfigBody, _: dict = Depends(_require_empresa)):

    config = load_config()
    bot = next((b for b in config["empresas"] if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="Nombre no puede ser vacío")
        bot["name"] = body.name.strip()

    if body.password is not None:
        if not body.password.strip():
            raise HTTPException(status_code=400, detail="Contraseña no puede ser vacía")
        for b in config["empresas"]:
            if b["id"] != bot_id and b.get("password") == body.password:
                raise HTTPException(status_code=409, detail="Esa contraseña ya está en uso")
        bot["password"] = body.password

    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": bot["name"]}


# ─── Gestión de conexiones Telegram ──────────────────────────────

class AddTelegramBody(BaseModel):
    token: str


@router.post("/empresa/{bot_id}/telegram")
async def empresa_add_telegram(bot_id: str, body: AddTelegramBody, _: dict = Depends(_require_empresa)):
    token = body.token.strip()
    if not token or ":" not in token:
        raise HTTPException(status_code=400, detail="Token inválido (formato: 123456789:ABC...)")

    token_id = token.split(":")[0]
    session_id = f"{bot_id}-tg-{token_id}"

    config = load_config()
    for b in config["empresas"]:
        for tg in b.get("telegram", []):
            if tg["token"].split(":")[0] == token_id:
                raise HTTPException(status_code=409, detail="Ese token ya está configurado")

    bot = next(b for b in config["empresas"] if b["id"] == bot_id)
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
            cfg = {"connection_id": bot_id, "token": token}
            tg_app = build_telegram_app(cfg)
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling(drop_pending_updates=True)
            _tg_apps.append(tg_app)
            clients[session_id] = {"status": "ready", "qr": None, "connection_id": bot_id, "type": "telegram", "client": tg_app}
        except Exception:
            requires_restart = True

    return {"ok": True, "session_id": session_id, "requires_restart": requires_restart}


@router.delete("/empresa/{bot_id}/telegram/{token_id}")
def empresa_remove_telegram(bot_id: str, token_id: str, _: dict = Depends(_require_empresa)):

    config = load_config()
    bot = next((b for b in config["empresas"] if b["id"] == bot_id), None)
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


@router.delete("/empresa/{bot_id}/suggested-contacts")
async def empresa_clear_suggested_contacts(
    bot_id: str,
    _: dict = Depends(_require_empresa),
):
    """Limpia todas las contact_suggestions de esta empresa."""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            text("DELETE FROM contact_suggestions WHERE empresa_id = :bid"),
            {"bid": bot_id},
        )
        await db_session.commit()
    return {"deleted": result.rowcount}


@router.put("/empresa/{bot_id}/paused")
async def set_empresa_paused(
    bot_id: str,
    body: dict,
    _: dict = Depends(_require_empresa_or_admin),
):
    """
    Pausa o reanuda el bot de una empresa.
    body: { "paused": true | false }
    Bot pausado = conexión viva pero sin replies automáticos.
    Acepta tanto JWT Bearer (empresa) como x-password (admin).
    """
    import paused as _paused_mod
    should_pause = bool(body.get("paused", False))
    if should_pause:
        _paused_mod.pause(bot_id)
    else:
        _paused_mod.resume(bot_id)
    return {"ok": True, "paused": should_pause, "empresa_id": bot_id}


@router.get("/empresa/{bot_id}/paused")
async def get_empresa_paused(
    bot_id: str,
    _: dict = Depends(_require_empresa_or_admin),
):
    import paused as _paused_mod
    return {"paused": _paused_mod.is_paused(bot_id), "empresa_id": bot_id}


@router.delete("/empresa/{bot_id}/suggested-contacts/{name}")
async def empresa_delete_one_suggestion(
    bot_id: str,
    name: str,
    _: dict = Depends(_require_empresa),
):
    """Elimina una sugerencia específica por nombre."""
    async with AsyncSessionLocal() as db_session:
        await db_session.execute(
            text("DELETE FROM contact_suggestions WHERE empresa_id = :bid AND name = :name"),
            {"bid": bot_id, "name": name},
        )
        await db_session.commit()
    return {"ok": True}
