"""
Registry de colecciones para búsqueda vectorial.

Cada colección tiene un handler que recibe (query: str, top_k: int, empresa_id: str)
y retorna dict con los datos encontrados.

Los handlers se registran usando @register_collection("nombre_colección")
"""
import logging

logger = logging.getLogger(__name__)

# Registry global de handlers
COLLECTION_REGISTRY: dict[str, object] = {}


def register_collection(name: str):
    """Decorador para registrar un handler de colección."""
    def decorator(fn):
        COLLECTION_REGISTRY[name] = fn
        logger.debug("[collections] Handler registrado para colección '%s'", name)
        return fn
    return decorator


def get_handler(collection: str):
    """Obtiene el handler para una colección, o None si no existe."""
    handler = COLLECTION_REGISTRY.get(collection)
    if not handler:
        logger.warning("[collections] Handler no encontrado para colección '%s'", collection)
        return None
    return handler


# Importar y registrar handlers de Luganense
from .luganense import register_luganense_handlers
register_luganense_handlers()

__all__ = ["register_collection", "get_handler", "COLLECTION_REGISTRY"]
