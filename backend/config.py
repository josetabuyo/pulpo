import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent  # worktree root
_CONNECTIONS_PATH = _ROOT / "connections.json"


def load_config() -> dict:
    with open(_CONNECTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(_CONNECTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_bot_for_connection(connection_id: str) -> str | None:
    """
    Retorna el bot_id al que pertenece este connection_id.
    Si la conexión pertenece a múltiples bots, devuelve el primero.
    Usar get_bots_for_connection() para el caso multi-bot.
    """
    results = get_bots_for_connection(connection_id)
    return results[0] if results else None


def get_bots_for_connection(connection_id: str) -> list[str]:
    """
    Retorna todos los bot_ids que tienen registrada esta conexión (connection_id).
    Una conexión puede ser un número WA, un session_id TG, o el propio bot id.
    Permite el dispatch multi-bot: si el mismo número está en varios bots,
    el mensaje se loguea bajo todos ellos.
    """
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        if bot["id"] == connection_id:
            if bot["id"] not in result:
                result.append(bot["id"])
            continue
        for phone in bot.get("phones", []):
            if phone["number"] == connection_id:
                if bot["id"] not in result:
                    result.append(bot["id"])
                break
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            if f"{bot['id']}-tg-{token_id}" == connection_id:
                if bot["id"] not in result:
                    result.append(bot["id"])
                break
    return result


def get_connection_default_filter(conn_id: str, bot_id: str | None = None) -> dict | None:
    """
    Retorna el default_filter configurado para una conexión (número WA).
    Se almacena bajo phones[].default_filter en connections.json.
    Si bot_id se provee, busca el filtro específico de esa bot (conexión compartida).
    Retorna None si no hay filtro configurado.
    """
    try:
        config = load_config()
    except Exception:
        return None
    for bot in config.get("bots", []):
        if bot_id and bot["id"] != bot_id:
            continue
        for phone in bot.get("phones", []):
            if phone.get("number") == conn_id:
                return phone.get("default_filter")
    return None


def set_connection_default_filter(conn_id: str, default_filter: dict | None, bot_id: str | None = None) -> bool:
    """
    Guarda (o elimina) el default_filter para una conexión en connections.json.
    Si bot_id se provee, solo actualiza el entry de esa bot (conexión compartida).
    Retorna True si encontró y modificó la conexión, False si no existe.
    """
    config = load_config()
    for bot in config.get("bots", []):
        if bot_id and bot["id"] != bot_id:
            continue
        for phone in bot.get("phones", []):
            if phone.get("number") == conn_id:
                if default_filter is None:
                    phone.pop("default_filter", None)
                else:
                    phone["default_filter"] = default_filter
                save_config(config)
                return True
    return False


def get_telegram_connections(config: dict) -> list[dict]:
    """Devuelve una lista de configs de conexiones Telegram: [{ connection_id, token }, ...]"""
    result = []
    for bot in config.get("bots", []):
        bot_id = bot["id"]
        for tg in bot.get("telegram", []):
            result.append({"connection_id": bot_id, "token": tg["token"]})
    return result


# ─── Global settings ──────────────────────────────────────────────────────────

def get_settings() -> dict:
    try:
        return load_config().get("settings", {})
    except Exception:
        return {}


def update_settings(patch: dict) -> dict:
    cfg = load_config()
    settings = cfg.setdefault("settings", {})
    settings.update(patch)
    save_config(cfg)
    return settings


def get_wa_poll_interval() -> int:
    return int(get_settings().get("wa_poll_interval_seconds", 300))
