import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent  # _/ worktree root
_CONNECTIONS_PATH = _ROOT / "connections.json"


def load_config() -> dict:
    with open(_CONNECTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(_CONNECTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_bot_for_connection(connection_id: str) -> str | None:
    results = get_bots_for_connection(connection_id)
    return results[0] if results else None


def get_bots_for_connection(connection_id: str) -> list[str]:
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
    result = []
    for bot in config.get("bots", []):
        bot_id = bot["id"]
        for tg in bot.get("telegram", []):
            result.append({"connection_id": bot_id, "token": tg["token"]})
    return result


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
