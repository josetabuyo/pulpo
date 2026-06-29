"""
Business logic for connection (phone/Google) management.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

import json
import uuid

from pulpo.core.config import (
    load_config,
    save_config,
    get_connection_default_filter,
    set_connection_default_filter,
)
from pulpo.core.state import clients
import pulpo.core.db as db


def list_connections() -> list[dict]:
    """Returns all phone connections with their session status."""
    from pulpo.core.state import wavi_status
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        for phone in bot.get("phones", []):
            session_id = phone["number"]
            result.append({
                "botId": bot["id"],
                "botName": bot["name"],
                "number": phone["number"],
                "sessionId": session_id,
                "status": wavi_status.get(session_id, "stopped"),
            })
    return result


def create_connection(bot_id: str, number: str, bot_name: str | None) -> dict:
    """
    Adds a phone number to a bot.
    Creates the bot entry if it doesn't exist (requires bot_name in that case).
    Raises ValueError if bot_id/number are missing, if bot not found without bot_name,
    or if the number already exists in the bot.
    """
    if not bot_id or not number:
        raise ValueError("botId y number son requeridos")

    config = load_config()
    bot = next((e for e in config.get("bots", []) if e["id"] == bot_id), None)

    if not bot:
        if not bot_name:
            raise ValueError("Bot nueva requiere botName")
        bot = {"id": bot_id, "name": bot_name, "phones": []}
        config.setdefault("bots", []).append(bot)

    if any(p["number"] == number for p in bot.get("phones", [])):
        raise ValueError(f"El número ya está en esta bot.")

    bot.setdefault("phones", []).append({"number": number})
    save_config(config)
    return {"ok": True, "sessionId": number}


def delete_connection(number: str) -> bool:
    """
    Removes a phone connection and cleans up its client.
    Returns True on success, False if number not found.
    """
    config = load_config()
    for bot in config.get("bots", []):
        idx = next((i for i, p in enumerate(bot.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            session_id = number
            if session_id in clients:
                try:
                    clients[session_id]["client"].destroy()
                except Exception:
                    pass
                del clients[session_id]
            bot["phones"].pop(idx)
            save_config(config)
            return True
    return False


def patch_connection_settings(number: str, allow_mass: bool) -> bool:
    """
    Updates allow_mass for a phone connection.
    Returns True on success, False if number not found.
    """
    config = load_config()
    for bot in config.get("bots", []):
        for phone in bot.get("phones", []):
            if phone.get("number") == number:
                phone["allow_mass"] = allow_mass
                save_config(config)
                return True
    return False


def move_connection(number: str, target_bot_id: str) -> dict:
    """
    Moves a phone number from one bot to another.
    Raises ValueError if target_bot_id is missing, not found, or number already in target.
    Raises KeyError if number not found.
    """
    if not target_bot_id:
        raise ValueError("targetBotId requerido")

    config = load_config()
    target_bot = next((e for e in config.get("bots", []) if e["id"] == target_bot_id), None)
    if not target_bot:
        raise KeyError(f"Bot destino no encontrada: {target_bot_id}")

    source_bot = None
    phone_entry = None
    for e in config.get("bots", []):
        idx = next((i for i, p in enumerate(e.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            source_bot = e
            phone_entry = e["phones"].pop(idx)
            break

    if not source_bot:
        raise KeyError(f"Número no encontrado: {number}")
    if source_bot["id"] == target_bot_id:
        raise ValueError("El teléfono ya está en esa bot")

    target_bot.setdefault("phones", []).append(phone_entry)
    save_config(config)
    return {"ok": True, "from": source_bot["id"], "to": target_bot_id}


def get_connection_filter(number: str, bot_id: str | None) -> dict:
    """
    Returns the default filter for a connection.
    Returns an empty filter dict if none is set.
    """
    df = get_connection_default_filter(number, bot_id)
    if df is None:
        return {"include_all_known": False, "include_unknown": False, "included": [], "excluded": []}
    return df


def set_connection_filter(number: str, filter_dict: dict, bot_id: str | None) -> bool:
    """
    Saves the default filter for a connection.
    Returns True on success, False if number not found.
    """
    return bool(set_connection_default_filter(number, filter_dict, bot_id))


def delete_connection_filter(number: str) -> bool:
    """
    Removes the default filter for a connection (admin only — caller enforces auth).
    Returns True on success, False if number not found.
    """
    return bool(set_connection_default_filter(number, None))


async def list_google_connections(bot_id: str) -> list[dict]:
    """Returns all Google connections for a bot."""
    return await db.get_google_connections(bot_id)


async def create_google_connection(bot_id: str, credentials_json: str, label: str | None) -> dict:
    """
    Creates a Google service account connection.
    Raises ValueError if credentials_json is invalid or missing required fields.
    """
    try:
        info = json.loads(credentials_json)
    except Exception:
        raise ValueError("credentials_json no es JSON válido")
    email = info.get("client_email", "")
    if not email or "private_key" not in info:
        raise ValueError("El JSON debe tener client_email y private_key")
    conn_id = str(uuid.uuid4())
    resolved_label = label or email.split("@")[0]
    await db.create_google_connection(
        id=conn_id,
        bot_id=bot_id,
        credentials_json=credentials_json,
        email=email,
        label=resolved_label,
    )
    return {"ok": True, "id": conn_id, "email": email, "label": resolved_label}


async def delete_google_connection(bot_id: str, conn_id: str) -> bool:
    """
    Deletes a Google connection.
    Raises PermissionError for the protected 'pulpo-default' connection.
    Raises KeyError if connection not found for this bot.
    Returns True on success.
    """
    if conn_id == "pulpo-default":
        raise PermissionError("La conexión Pulpo no se puede eliminar")
    conns = await db.get_google_connections(bot_id)
    if not any(c["id"] == conn_id for c in conns):
        raise KeyError(f"Conexión no encontrada para esta bot: {conn_id}")
    ok = await db.delete_google_connection(conn_id)
    if not ok:
        raise KeyError(f"Conexión no encontrada: {conn_id}")
    return True
