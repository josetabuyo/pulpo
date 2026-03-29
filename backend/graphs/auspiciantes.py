"""
Módulo de auspiciantes: carga la config por empresa y devuelve un auspiciante random.
"""
import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config" / "auspiciantes"


def get_random(empresa_id: str) -> str | None:
    """
    Devuelve el mensaje de un auspiciante activo random para la empresa dada.
    Retorna None si no hay config o no hay auspiciantes activos.
    """
    config_path = _CONFIG_DIR / f"{empresa_id}.json"
    if not config_path.exists():
        logger.debug("[auspiciantes] Sin config para empresa '%s'", empresa_id)
        return None

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("[auspiciantes] Error leyendo config de '%s': %s", empresa_id, e)
        return None

    activos = [a for a in data.get("auspiciantes", []) if a.get("activo")]
    if not activos:
        return None

    elegido = random.choice(activos)
    logger.info("[auspiciantes] Auspiciante elegido: %s", elegido["nombre"])
    return elegido["mensaje"]
