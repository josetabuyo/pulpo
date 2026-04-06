"""
VectorSearchNode — búsqueda genérica parametrizada por colección.

Config:
  collection:    str — nombre de la colección registrada (ej: "luganense_oficios", "luganense_auspiciantes")
  query_field:   str — dónde leer el query: "message" | "query" | "context" (default: "message")
  output_field:  str — dónde escribir el resultado: "context" | "query" (default: "context")
  top_k:         int — cantidad de resultados (default: 3)

El nodo:
1. Lee el query del campo especificado en config, interpolando placeholders
2. Busca en la colección usando el handler registrado
3. Escribe los resultados en state.vars (con las keys del dict retornado)
4. Escribe el texto principal en state[output_field]

Si el handler no existe, loguea warning y continúa sin romper el flow.
"""
import json
import logging
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


class VectorSearchNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        collection = self.config.get("collection")
        if not collection:
            logger.warning("[VectorSearchNode] No se especificó 'collection'")
            return state

        query_field = self.config.get("query_field", "message")
        output_field = self.config.get("output_field", "context")
        top_k = self.config.get("top_k", 3)

        # Leer el query del campo especificado
        query = self._get_query_from_field(state, query_field)
        if not query:
            logger.warning("[VectorSearchNode] Query vacía del campo '%s'", query_field)
            return state

        # Interpolar placeholders
        query = interpolate(query, state)

        # Buscar en la colección
        try:
            from graphs.collections import get_handler
            handler = get_handler(collection)
            if not handler:
                logger.warning("[VectorSearchNode] Handler no registrado para colección '%s'", collection)
                return state

            # Llamar al handler: (query: str, top_k: int, empresa_id: str) → dict
            result = await handler(query, top_k, state.empresa_id) if handler else {}
            if not result:
                logger.info("[VectorSearchNode] Sin resultados para colección '%s'", collection)
                return state

            # Escribir en state.vars con las keys del resultado
            for key, value in result.items():
                state.vars[key] = value
                logger.debug("[VectorSearchNode] vars['%s'] = %s", key, value)

            # Escribir el texto principal en output_field
            # Buscamos primero una key "text" o "mensaje" en el resultado, sino serializamos todo
            text_output = result.get("text") or result.get("mensaje") or json.dumps(result, ensure_ascii=False)
            if output_field == "context":
                state.context = text_output
            elif output_field == "query":
                state.query = text_output
            else:
                logger.warning("[VectorSearchNode] output_field desconocido: '%s'", output_field)

            logger.info("[VectorSearchNode] Resultado guardado en '%s' (colección: '%s')", output_field, collection)
        except Exception as e:
            logger.error("[VectorSearchNode] Error buscando en colección '%s': %s", collection, e)

        return state

    def _get_query_from_field(self, state: FlowState, field: str) -> str:
        """Lee el query del campo especificado."""
        if field == "message":
            return state.message
        elif field == "query":
            return state.query
        elif field == "context":
            return state.context
        else:
            logger.warning("[VectorSearchNode] query_field desconocido: '%s'", field)
            return ""

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "collection": {
                "type": "string",
                "label": "Colección",
                "required": True,
                "default": "luganense_oficios",
            },
            "query_field": {
                "type": "select",
                "label": "Dónde leer el query",
                "default": "message",
                "options": ["message", "query", "context"],
            },
            "output_field": {
                "type": "select",
                "label": "Dónde escribir el resultado",
                "default": "context",
                "options": ["context", "query"],
            },
            "top_k": {
                "type": "float",
                "label": "Cantidad de resultados",
                "default": 3,
            },
        }
