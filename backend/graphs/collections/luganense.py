"""
Handlers de colecciones para Luganense.

Wrappea la lógica existente de auspiciantes y workers,
exponiéndola como handlers registrados del registry de colecciones.
"""
import json
import logging
from . import register_collection

logger = logging.getLogger(__name__)


@register_collection("luganense_oficios")
async def handler_luganense_oficios(query: str, top_k: int, empresa_id: str) -> dict:
    """
    Handler para búsqueda de oficios (workers) en Luganense.

    Retorna:
      {
          "oficio": str — oficio identificado,
          "worker": dict | None — datos del worker,
          "nombre": str — nombre del worker (si existe),
          "telefono": str — teléfono del worker (si existe),
      }
    """
    try:
        import sys
        from pathlib import Path
        backend_path = Path(__file__).parent.parent.parent
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        from nodes import find_worker
        oficio, worker = await find_worker.find(query, empresa_id)

        result = {
            "oficio": oficio,
            "worker": worker,
        }

        if worker:
            result["nombre"] = worker.get("nombre", "")
            result["telefono"] = worker.get("telefono", "")
            result["text"] = json.dumps({"oficio": oficio, "worker": worker}, ensure_ascii=False)
        else:
            result["nombre"] = ""
            result["telefono"] = ""
            result["text"] = json.dumps({"oficio": oficio, "worker": None}, ensure_ascii=False)

        logger.info("[luganense_oficios] Handler: oficio='%s', worker=%s", oficio, worker["nombre"] if worker else None)
        return result
    except Exception as e:
        logger.error("[luganense_oficios] Error: %s", e)
        return {
            "oficio": "otro",
            "worker": None,
            "nombre": "",
            "telefono": "",
            "text": json.dumps({"oficio": "otro", "worker": None}, ensure_ascii=False),
        }


@register_collection("luganense_auspiciantes")
async def handler_luganense_auspiciantes(query: str, top_k: int, empresa_id: str) -> dict:
    """
    Handler para búsqueda de auspiciantes en Luganense.

    Retorna:
      {
          "nombre": str — nombre del auspiciante,
          "mensaje": str — mensaje del auspiciante,
          "text": str — mensaje (mismo que mensaje),
      }
    """
    try:
        import sys
        from pathlib import Path
        backend_path = Path(__file__).parent.parent.parent
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        from graphs import auspiciantes as auspiciantes_mod
        nombre, mensaje = auspiciantes_mod.get_relevant(empresa_id, query)

        if mensaje:
            result = {
                "nombre": nombre or "",
                "mensaje": mensaje,
                "text": mensaje,
            }
            logger.info("[luganense_auspiciantes] Handler: match '%s'", nombre)
        else:
            result = {
                "nombre": "",
                "mensaje": "",
                "text": "",
            }
            logger.info("[luganense_auspiciantes] Handler: sin match")

        return result
    except Exception as e:
        logger.error("[luganense_auspiciantes] Error: %s", e)
        return {
            "nombre": "",
            "mensaje": "",
            "text": "",
        }


def register_luganense_handlers():
    """
    Función llamada desde __init__.py para registrar todos los handlers de Luganense.
    Los decoradores @register_collection ya los registraron, esta función es para
    futura extensión.
    """
    logger.info("[luganense] Handlers de Luganense registrados")
