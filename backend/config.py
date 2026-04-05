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


def get_empresa_for_connection(connection_id: str) -> str | None:
    """
    Retorna el empresa_id al que pertenece este connection_id.
    Si la conexión pertenece a múltiples empresas, devuelve el primero.
    Usar get_empresas_for_connection() para el caso multi-empresa.
    """
    results = get_empresas_for_connection(connection_id)
    return results[0] if results else None


def get_empresas_for_connection(connection_id: str) -> list[str]:
    """
    Retorna todos los empresa_ids que tienen registrada esta conexión (connection_id).
    Una conexión puede ser un número WA, un session_id TG, o el propio empresa id.
    Permite el dispatch multi-empresa: si el mismo número está en varios bots,
    el mensaje se loguea bajo todos ellos.
    """
    config = load_config()
    result = []
    for empresa in config.get("empresas", []):
        if empresa["id"] == connection_id:
            if empresa["id"] not in result:
                result.append(empresa["id"])
            continue
        for phone in empresa.get("phones", []):
            if phone["number"] == connection_id:
                if empresa["id"] not in result:
                    result.append(empresa["id"])
                break
        for tg in empresa.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            if f"{empresa['id']}-tg-{token_id}" == connection_id:
                if empresa["id"] not in result:
                    result.append(empresa["id"])
                break
    return result


def get_telegram_connections(config: dict) -> list[dict]:
    """Devuelve una lista de configs de conexiones Telegram: [{ connection_id, token }, ...]"""
    result = []
    for empresa in config.get("empresas", []):
        empresa_id = empresa["id"]
        for tg in empresa.get("telegram", []):
            result.append({"connection_id": empresa_id, "token": tg["token"]})
    return result
