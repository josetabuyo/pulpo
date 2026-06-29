"""
Business logic for contact management.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

import re

import pulpo.core.db as db

_TG_RE = re.compile(r"^(@\w+|\d+)$")


def _validate_channel_value(type: str, value: str, is_group: bool = False) -> str | None:
    """Returns an error message string or None if valid."""
    if type == "telegram":
        if not _TG_RE.match(value):
            return "El valor Telegram debe ser un número o @username"
    return None


async def list_contacts(bot_id: str) -> list[dict]:
    """Returns all contacts for a bot."""
    return await db.get_contacts(bot_id)


async def create_contact(bot_id: str, name: str, channels: list[dict]) -> dict:
    """
    Creates a contact and optionally adds channels.
    Raises ValueError on blank name, invalid channel type, or invalid channel value.
    Raises ValueError if a channel is already assigned to another contact.
    Returns the full contact dict.
    """
    name = name.strip()
    if not name:
        raise ValueError("El nombre es obligatorio")

    for ch in channels:
        ch_type = ch.get("type", "")
        ch_value = ch.get("value", "").strip()
        if ch_type not in ("telegram",):
            raise ValueError(f"Tipo de canal inválido: {ch_type}")
        err = _validate_channel_value(ch_type, ch_value, ch.get("is_group", False))
        if err:
            raise ValueError(err)

    contact_id = await db.create_contact(bot_id, name)

    for ch in channels:
        ch_type = ch.get("type", "")
        ch_value = ch.get("value", "").strip()
        is_group = ch.get("is_group", False)
        try:
            await db.add_channel(contact_id, ch_type, ch_value, is_group)
        except Exception:
            raise ValueError(f"El canal {ch_type}:{ch_value} ya está asignado a otro contacto")

    return await db.get_contact(contact_id)


async def get_contact(contact_id: int) -> dict | None:
    """Returns a contact dict or None if not found."""
    return await db.get_contact(contact_id)


async def update_contact(contact_id: int, name: str) -> dict | None:
    """
    Updates a contact's name.
    Returns the updated contact dict or None if not found.
    Raises ValueError on blank name.
    """
    contact = await db.get_contact(contact_id)
    if not contact:
        return None
    name = name.strip()
    if not name:
        raise ValueError("El nombre es obligatorio")
    await db.update_contact(contact_id, name)
    return await db.get_contact(contact_id)


async def delete_contact(contact_id: int) -> bool:
    """
    Deletes a contact.
    Returns True on success, False if not found.
    """
    contact = await db.get_contact(contact_id)
    if not contact:
        return False
    await db.delete_contact(contact_id)
    return True


async def add_channel(contact_id: int, type: str, value: str, is_group: bool) -> dict:
    """
    Adds a channel to a contact.
    Raises ValueError on invalid type or value, or if channel already assigned.
    Returns the channel dict.
    """
    if type not in ("telegram",):
        raise ValueError(f"Tipo de canal inválido: {type}")
    value = value.strip()
    err = _validate_channel_value(type, value, is_group)
    if err:
        raise ValueError(err)
    try:
        channel_id = await db.add_channel(contact_id, type, value, is_group)
    except Exception:
        raise ValueError(f"El canal {type}:{value} ya está asignado a otro contacto")
    return {"id": channel_id, "contact_id": contact_id, "type": type, "value": value, "is_group": is_group}


async def delete_channel(channel_id: int) -> bool:
    """
    Deletes a channel.
    Returns True on success, False if not found.
    """
    return await db.delete_channel(channel_id)
