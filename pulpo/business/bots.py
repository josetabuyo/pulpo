"""
Business logic for bot management.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

from pulpo.core.config import load_config, save_config
from pulpo.core.state import clients, wavi_status


def list_bots() -> list[dict]:
    """Returns all bots with phone and telegram session status."""
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        phones = []
        for phone in bot.get("phones", []):
            session_id = phone["number"]
            phones.append({
                "number": phone["number"],
                "alias": phone.get("alias", ""),
                "sessionId": session_id,
                "status": wavi_status.get(session_id, "stopped"),
                "allowMass": phone.get("allow_mass", False),
            })
        telegram = []
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            session_id = f"{bot['id']}-tg-{token_id}"
            tg_client = clients.get(session_id, {})
            telegram.append({
                "tokenId": token_id,
                "sessionId": session_id,
                "status": tg_client.get("status", "stopped"),
                "username": tg_client.get("bot_username", ""),
                "botName": tg_client.get("bot_name", ""),
                "allowMass": tg.get("allow_mass", False),
            })
        result.append({
            "id": bot["id"],
            "name": bot["name"],
            "phones": phones,
            "telegram": telegram,
        })
    return result


def get_bot(bot_id: str) -> dict | None:
    """Returns a single bot dict or None if not found."""
    config = load_config()
    return next((b for b in config.get("bots", []) if b["id"] == bot_id), None)


def create_bot(id: str, name: str, password: str) -> dict:
    """
    Creates a new bot.
    Raises ValueError if id/name/password are blank or if the id already exists.
    """
    if not id.strip() or not name.strip() or not password.strip():
        raise ValueError("id, name y password son requeridos")
    config = load_config()
    if any(b["id"] == id for b in config.get("bots", [])):
        raise ValueError(f"Ya existe una bot con ese id: {id}")
    config.setdefault("bots", []).append({
        "id": id,
        "name": name,
        "password": password,
        "phones": [],
        "telegram": [],
    })
    save_config(config)
    return {"ok": True, "id": id}


def update_bot(bot_id: str, name: str | None) -> bool:
    """
    Updates bot fields.
    Returns True on success, False if bot not found.
    """
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        return False
    if name:
        bot["name"] = name
    save_config(config)
    return True


def delete_bot(bot_id: str) -> bool:
    """
    Deletes a bot and cleans up its active clients.
    Returns True on success, False if bot not found.
    """
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        return False

    for phone in bot.get("phones", []):
        session_id = phone["number"]
        if session_id in clients:
            try:
                clients[session_id]["client"].destroy()
            except Exception:
                pass
            del clients[session_id]

    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        session_id = f"{bot_id}-tg-{token_id}"
        if session_id in clients:
            try:
                clients[session_id]["client"].stop_polling()
            except Exception:
                pass
            del clients[session_id]

    config["bots"] = [b for b in config["bots"] if b["id"] != bot_id]
    save_config(config)
    return True


def patch_telegram_settings(bot_id: str, token_id: str, allow_mass: bool) -> dict:
    """
    Updates allow_mass setting for a telegram connection.
    Raises KeyError if bot or telegram connection not found.
    """
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise KeyError(f"Bot no encontrado: {bot_id}")
    for tg in bot.get("telegram", []):
        if tg["token"].split(":")[0] == token_id:
            tg["allow_mass"] = allow_mass
            save_config(config)
            return {"ok": True, "allow_mass": allow_mass}
    raise KeyError(f"Conexión Telegram no encontrada: {token_id}")
