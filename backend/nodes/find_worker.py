"""
Node: find_worker

Dado un mensaje de un vecino:
1. Usa el LLM para identificar el oficio específico que busca.
2. Carga la lista de trabajadores de backend/config/oficios/{empresa_id}.json.
3. Devuelve el primer trabajador activo disponible para ese oficio.

Retorna: (oficio_str, worker_dict | None)
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config" / "oficios"
_MODEL = "llama-3.3-70b-versatile"

_IDENTIFY_SYSTEM = """Sos un clasificador de oficios para un bot de barrio.
Dado un mensaje de un vecino que busca un servicio, identificá el oficio en UNA sola palabra en minúsculas.

Oficios válidos: herrero, electricista, plomero, albanil, pintor, gasista, carpintero, mecanico, jardinero, techista, otro

Si no reconocés un oficio específico, respondé "otro".
Respondé SOLO la palabra del oficio. Sin explicaciones."""


async def find(message: str, empresa_id: str) -> tuple[str, dict | None]:
    """
    Identifica el oficio del mensaje y busca un trabajador disponible.
    Retorna (oficio, worker) — worker puede ser None si no hay disponibles.
    """
    oficio = await _identify_oficio(message)
    worker = _lookup_worker(empresa_id, oficio)
    logger.info("[find_worker] oficio='%s' worker=%s", oficio, worker["nombre"] if worker else None)
    return oficio, worker


async def _identify_oficio(message: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("[find_worker] GROQ_API_KEY no configurada, usando 'otro'")
        return "otro"

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_MODEL, api_key=api_key, max_tokens=10, temperature=0)
        result = await llm.ainvoke([
            {"role": "system", "content": _IDENTIFY_SYSTEM},
            {"role": "user", "content": message},
        ])
        oficio = result.content.strip().lower()
        logger.info("[find_worker] LLM identificó oficio: '%s'", oficio)
        return oficio
    except Exception as e:
        logger.error("[find_worker] Error identificando oficio: %s", e)
        return "otro"


def _lookup_worker(empresa_id: str, oficio: str) -> dict | None:
    config_path = _CONFIG_DIR / f"{empresa_id}.json"
    if not config_path.exists():
        logger.debug("[find_worker] Sin config de oficios para empresa '%s'", empresa_id)
        return None

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("[find_worker] Error leyendo config '%s': %s", empresa_id, e)
        return None

    lista = data.get("oficios", {}).get(oficio, [])
    activos = [w for w in lista if w.get("activo")]
    if not activos:
        return None

    worker = activos[0]
    worker["oficio"] = oficio
    return worker
