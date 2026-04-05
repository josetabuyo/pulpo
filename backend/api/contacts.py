import re
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from pydantic import BaseModel
from sqlalchemy import text

import db
from db import AsyncSessionLocal
from middleware_auth import get_empresa_id_from_token
from api.deps import ADMIN_PASSWORD

router = APIRouter()

_ADMIN_SENTINEL = "__admin__"


def _require_empresa_or_admin(request: Request, x_password: str = Header(default=None)) -> str:
    """Acepta admin x-password o JWT de empresa. Retorna empresa_id o '__admin__'."""
    if x_password == ADMIN_PASSWORD:
        return _ADMIN_SENTINEL
    empresa_id = get_empresa_id_from_token(request)
    if not empresa_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return empresa_id


# ─── Validaciones ────────────────────────────────────────────────

_TG_RE  = re.compile(r"^(@\w+|\d+)$")

def _validate_channel_value(type: str, value: str, is_group: bool = False) -> str | None:
    """Retorna mensaje de error o None si es válido."""
    if type == "whatsapp":
        if not value:
            return "El valor WhatsApp no puede estar vacío"
        # Los grupos WA tienen nombre (texto), no número
        if not is_group and not value.isdigit():
            return "El valor WhatsApp debe ser numérico (sin +, espacios ni guiones)"
    elif type == "telegram":
        if not _TG_RE.match(value):
            return "El valor Telegram debe ser un número o @username"
    return None


# ─── Schemas ─────────────────────────────────────────────────────

class ChannelIn(BaseModel):
    type: str
    value: str
    is_group: bool = False

class ContactIn(BaseModel):
    name: str
    channels: list[ChannelIn] = []

class ContactUpdate(BaseModel):
    name: str


# ─── Endpoints ───────────────────────────────────────────────────

def _check_auth(bot_id: str, token_empresa_id: str):
    if token_empresa_id == _ADMIN_SENTINEL:
        return  # admin puede acceder a cualquier empresa
    if token_empresa_id != bot_id:
        raise HTTPException(403, "No autorizado para esta empresa")


@router.get("/bots/{bot_id}/contacts")
async def list_contacts(bot_id: str, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    _check_auth(bot_id, token_empresa_id)
    return await db.get_contacts(bot_id)


@router.post("/bots/{bot_id}/contacts", status_code=201)
async def create_contact(bot_id: str, body: ContactIn, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    _check_auth(bot_id, token_empresa_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "El nombre es obligatorio")

    for ch in body.channels:
        if ch.type not in ("whatsapp", "telegram"):
            raise HTTPException(400, f"Tipo de canal inválido: {ch.type}")
        err = _validate_channel_value(ch.type, ch.value.strip(), ch.is_group)
        if err:
            raise HTTPException(400, err)

    contact_id = await db.create_contact(bot_id, name)

    for ch in body.channels:
        try:
            await db.add_channel(contact_id, ch.type, ch.value.strip(), ch.is_group)
        except Exception:
            raise HTTPException(409, f"El canal {ch.type}:{ch.value} ya está asignado a otro contacto")

    return await db.get_contact(contact_id)


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: int, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    contact = await db.get_contact(contact_id)
    if not contact:
        raise HTTPException(404, "Contacto no encontrado")
    _check_auth(contact["bot_id"], token_empresa_id)
    return contact


@router.put("/contacts/{contact_id}")
async def update_contact(contact_id: int, body: ContactUpdate, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    contact = await db.get_contact(contact_id)
    if not contact:
        raise HTTPException(404, "Contacto no encontrado")
    _check_auth(contact["bot_id"], token_empresa_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "El nombre es obligatorio")
    await db.update_contact(contact_id, name)
    return await db.get_contact(contact_id)


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: int, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    contact = await db.get_contact(contact_id)
    if not contact:
        raise HTTPException(404, "Contacto no encontrado")
    _check_auth(contact["bot_id"], token_empresa_id)
    await db.delete_contact(contact_id)


@router.post("/contacts/{contact_id}/channels", status_code=201)
async def add_channel(contact_id: int, body: ChannelIn, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    contact = await db.get_contact(contact_id)
    if not contact:
        raise HTTPException(404, "Contacto no encontrado")
    _check_auth(contact["bot_id"], token_empresa_id)
    if body.type not in ("whatsapp", "telegram"):
        raise HTTPException(400, f"Tipo de canal inválido: {body.type}")
    err = _validate_channel_value(body.type, body.value.strip(), body.is_group)
    if err:
        raise HTTPException(400, err)
    try:
        channel_id = await db.add_channel(contact_id, body.type, body.value.strip(), body.is_group)
    except Exception:
        raise HTTPException(409, f"El canal {body.type}:{body.value} ya está asignado a otro contacto")
    return {"id": channel_id, "contact_id": contact_id, "type": body.type, "value": body.value.strip(), "is_group": body.is_group}


@router.delete("/contact-channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: int, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    ok = await db.delete_channel(channel_id)
    if not ok:
        raise HTTPException(404, "Canal no encontrado")


@router.get("/bots/{bot_id}/contacts/suggested")
async def suggested_contacts(bot_id: str, token_empresa_id: str = Depends(_require_empresa_or_admin)):
    _check_auth(bot_id, token_empresa_id)
    """Senders que escribieron pero no están en contact_channels (whatsapp)."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT DISTINCT m.phone, m.name
            FROM messages m
            WHERE m.bot_id = :bot_id
              AND m.outbound = 0
              AND m.phone NOT IN (
                  SELECT cc.value FROM contact_channels cc WHERE cc.type = 'whatsapp'
              )
            ORDER BY m.phone
        """), {"bot_id": bot_id})).fetchall()
    return [{"phone": r[0], "name": r[1]} for r in rows]
