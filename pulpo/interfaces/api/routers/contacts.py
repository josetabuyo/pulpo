"""
Router: /contacts

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Route layout (parent mounts at /contacts):
  GET    /bots/{bot_id}/contacts
  POST   /bots/{bot_id}/contacts
  GET    /{contact_id}
  PUT    /{contact_id}
  DELETE /{contact_id}
  POST   /{contact_id}/channels
  DELETE /contact-channels/{channel_id}
"""
import re
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from pulpo.business import contacts as contacts_svc

router = APIRouter()

_TG_RE = re.compile(r"^(@\w+|\d+)$")


def _validate_channel_value(type: str, value: str, is_group: bool = False) -> str | None:
    """Retorna mensaje de error o None si es válido."""
    if type == "telegram":
        if not _TG_RE.match(value):
            return "El valor Telegram debe ser un número o @username"
    return None


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ChannelIn(BaseModel):
    type: str
    value: str
    is_group: bool = False


class ContactIn(BaseModel):
    name: str
    channels: list[ChannelIn] = []


class ContactUpdate(BaseModel):
    name: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/bots/{bot_id}/contacts")
async def list_contacts(bot_id: str):
    try:
        return await contacts_svc.list_contacts(bot_id=bot_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bots/{bot_id}/contacts", status_code=201)
async def create_contact(bot_id: str, body: ContactIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "El nombre es obligatorio")

    for ch in body.channels:
        if ch.type not in ("telegram",):
            raise HTTPException(400, f"Tipo de canal inválido: {ch.type}")
        err = _validate_channel_value(ch.type, ch.value.strip(), ch.is_group)
        if err:
            raise HTTPException(400, err)

    try:
        return await contacts_svc.create_contact(
            bot_id=bot_id,
            name=name,
            channels=[{"type": ch.type, "value": ch.value.strip(), "is_group": ch.is_group} for ch in body.channels],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{contact_id}")
async def get_contact(contact_id: int):
    try:
        contact = await contacts_svc.get_contact(contact_id=contact_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if contact is None:
        raise HTTPException(status_code=404, detail=f"Contacto {contact_id} no encontrado")
    return contact


@router.put("/{contact_id}")
async def update_contact(contact_id: int, body: ContactUpdate):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "El nombre es obligatorio")
    try:
        return await contacts_svc.update_contact(contact_id=contact_id, name=name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: int):
    try:
        found = await contacts_svc.delete_contact(contact_id=contact_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not found:
        raise HTTPException(status_code=404, detail=f"Contacto {contact_id} no encontrado")
    return Response(status_code=204)


@router.post("/{contact_id}/channels", status_code=201)
async def add_channel(contact_id: int, body: ChannelIn):
    if body.type not in ("telegram",):
        raise HTTPException(400, f"Tipo de canal inválido: {body.type}")
    err = _validate_channel_value(body.type, body.value.strip(), body.is_group)
    if err:
        raise HTTPException(400, err)
    try:
        return await contacts_svc.add_channel(
            contact_id=contact_id,
            type=body.type,
            value=body.value.strip(),
            is_group=body.is_group,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/contact-channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: int):
    try:
        await contacts_svc.delete_channel(channel_id=channel_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)
