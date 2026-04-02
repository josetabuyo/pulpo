"""
Módulo de auspiciantes: carga la config por empresa y busca el auspiciante más relevante.
"""
import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config" / "auspiciantes"


def _load_activos(empresa_id: str) -> list[dict]:
    config_path = _CONFIG_DIR / f"{empresa_id}.json"
    if not config_path.exists():
        logger.debug("[auspiciantes] Sin config para empresa '%s'", empresa_id)
        return []
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        return [a for a in data.get("auspiciantes", []) if a.get("activo")]
    except Exception as e:
        logger.error("[auspiciantes] Error leyendo config de '%s': %s", empresa_id, e)
        return []


def get_relevant(empresa_id: str, message: str) -> tuple[str, str] | tuple[None, None]:
    """
    Busca el auspiciante más relevante para el mensaje del usuario.
    Matchea por tags: cuenta cuántos tags del auspiciante aparecen en el mensaje.
    Retorna (nombre, mensaje) del mejor match, o (None, None) si no hay match.
    """
    activos = _load_activos(empresa_id)
    if not activos:
        return None, None

    message_lower = message.lower()
    best = None
    best_score = 0

    for a in activos:
        score = sum(1 for tag in a.get("tags", []) if tag.lower() in message_lower)
        if score > best_score:
            best_score = score
            best = a

    if best and best_score > 0:
        logger.info("[auspiciantes] match por tags (score=%d): %s", best_score, best["nombre"])
        return best["nombre"], best["mensaje"]

    return None, None


def get_random(empresa_id: str) -> str | None:
    """Devuelve el mensaje de un auspiciante activo random. Uso legado."""
    activos = _load_activos(empresa_id)
    if not activos:
        return None
    elegido = random.choice(activos)
    logger.info("[auspiciantes] Auspiciante random: %s", elegido["nombre"])
    return elegido["mensaje"]
