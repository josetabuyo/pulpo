import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent  # worktree root
_PHONES_PATH = _ROOT / "phones.json"


def load_config() -> dict:
    with open(_PHONES_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(_PHONES_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_empresa_for_bot(bot_id: str) -> str | None:
    """
    Retorna el empresa_id al que pertenece este bot_id.
    En phones.json, el 'id' del bot es el empresa_id.
    Los números WA y session TG pertenecen al bot que los contiene.
    """
    config = load_config()
    for bot in config.get("bots", []):
        # El bot_id directo
        if bot["id"] == bot_id:
            return bot["id"]
        # Números WA
        for phone in bot.get("phones", []):
            if phone["number"] == bot_id:
                return bot["id"]
        # Sessions TG
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            if f"{bot['id']}-tg-{token_id}" == bot_id:
                return bot["id"]
    return None


def get_telegram_bots(config: dict) -> list[dict]:
    """
    Devuelve una lista de configs de bots de Telegram:
    [{ bot_id, token, allowed_contacts, reply_message }, ...]
    """
    result = []
    for bot in config.get("bots", []):
        bot_id = bot["id"]
        bot_reply = bot.get("autoReplyMessage", "")
        for tg in bot.get("telegram", []):
            reply = tg.get("autoReplyMessage") or bot_reply
            result.append({
                "bot_id": bot_id,
                "token": tg["token"],
                "allowed_contacts": [str(c).lower() for c in tg.get("allowedContacts", [])],
                "reply_message": reply,
            })
    return result
