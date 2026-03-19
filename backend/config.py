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
    Si el bot pertenece a múltiples empresas, devuelve el primero.
    Usar get_empresas_for_bot() para el caso multi-empresa.
    """
    results = get_empresas_for_bot(bot_id)
    return results[0] if results else None


def get_empresas_for_bot(bot_id: str) -> list[str]:
    """
    Retorna todos los empresa_ids que contienen este bot_id.
    Un mismo número WA puede estar en múltiples empresas (conexión compartida).
    """
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        if bot["id"] == bot_id:
            result.append(bot["id"])
            continue
        for phone in bot.get("phones", []):
            if phone["number"] == bot_id:
                result.append(bot["id"])
                break
        else:
            for tg in bot.get("telegram", []):
                token_id = tg["token"].split(":")[0]
                if f"{bot['id']}-tg-{token_id}" == bot_id:
                    result.append(bot["id"])
                    break
    return result


def get_empresas_for_bot(bot_id: str) -> list[str]:
    """
    Retorna todos los empresa_ids que tienen registrada esta conexión (bot_id).
    Una conexión puede ser un número WA, un session_id TG, o el propio bot_id.
    Permite el dispatch multi-empresa: si el mismo número está en varios bots,
    el mensaje se loguea bajo todos ellos.
    """
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        if bot["id"] == bot_id:
            if bot["id"] not in result:
                result.append(bot["id"])
            continue
        for phone in bot.get("phones", []):
            if phone["number"] == bot_id:
                if bot["id"] not in result:
                    result.append(bot["id"])
                break
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            if f"{bot['id']}-tg-{token_id}" == bot_id:
                if bot["id"] not in result:
                    result.append(bot["id"])
                break
    return result


def get_telegram_bots(config: dict) -> list[dict]:
    """
    Devuelve una lista de configs de bots de Telegram:
    [{ bot_id, token, reply_message }, ...]
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
                "reply_message": reply,
            })
    return result
