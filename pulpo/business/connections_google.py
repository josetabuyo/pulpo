"""
Business logic for Google service-account connections (bot-scoped).
Persistencia: DB (pulpo.core.db) — async, independiente de connections.json.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

import json
import uuid

import pulpo.core.db as db


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
