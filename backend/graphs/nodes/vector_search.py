"""
VectorSearchNode — búsqueda en una colección de ítems.

Dos modos según config:

  mode = "registry" (default)
    collection: str — nombre de la colección registrada en COLLECTION_REGISTRY
    Usa handlers externos (luganense_oficios, etc.)

  mode = "inline"
    items:        list[dict] — lista de ítems editable desde la UI
    search_field: str        — campo por el que se busca (default: "oficio")
    La búsqueda usa el LLM para extraer el valor del search_field del mensaje,
    luego filtra items con normalización de género.

En ambos modos escribe en state.vars todas las keys del resultado,
y el campo "text" va a state.context.
"""
import json
import logging
import os
import re
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


# ─── Normalización de género ──────────────────────────────────────────────────

def _normalize(word: str) -> str:
    """
    Normaliza una palabra para búsqueda sin distinción de género.
    "abogada" → "abogad", "herrero" → "herrer", "electricista" → "electricist"
    Funciona quitando la vocal terminal si es a/o.
    """
    w = word.strip().lower()
    if w.endswith(("ista", "nte", "or")):
        return w  # sin inflexión de género
    if w.endswith(("a", "o")):
        return w[:-1]
    return w


def _match(query_value: str, item_value: str) -> bool:
    """True si los valores coinciden con normalización de género."""
    return _normalize(query_value) == _normalize(item_value)


# ─── Extracción del valor de búsqueda via LLM ────────────────────────────────

_IDENTIFY_SYSTEM = """Sos un extractor de valores para un sistema de búsqueda.
Dado un mensaje, identificá el valor del campo "{field}" en UNA sola palabra en minúsculas.
Valores posibles: {values}
Si no encontrás un valor claro, respondé "otro".
Respondé SOLO la palabra. Sin explicaciones."""


async def _identify_field_value(message: str, search_field: str, possible_values: list[str]) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "otro"

    values_str = ", ".join(possible_values) if possible_values else "cualquier valor relevante"
    system = _IDENTIFY_SYSTEM.format(field=search_field, values=values_str)

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=api_key, max_tokens=10, temperature=0)
        result = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ])
        value = result.content.strip().lower()
        logger.info("[VectorSearchNode] LLM identificó %s='%s'", search_field, value)
        return value
    except Exception as e:
        logger.error("[VectorSearchNode] Error identificando %s: %s", search_field, e)
        return "otro"


# ─── Nodo ─────────────────────────────────────────────────────────────────────

class VectorSearchNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        mode = self.config.get("mode", "registry")

        if mode == "inline":
            return await self._run_inline(state)
        else:
            return await self._run_registry(state)

    # ── Modo inline ────────────────────────────────────────────────────────────

    async def _run_inline(self, state: FlowState) -> FlowState:
        items = self.config.get("items", [])
        search_field = self.config.get("search_field", "oficio")

        if not items:
            logger.warning("[VectorSearchNode] items vacío")
            return state

        query = interpolate(state.message, state)

        # Obtener valores posibles del campo de búsqueda para orientar al LLM
        possible_values = list({
            item.get(search_field, "").lower()
            for item in items
            if item.get(search_field)
        })

        # LLM extrae el valor buscado del mensaje
        search_value = await _identify_field_value(query, search_field, possible_values)

        # Filtrar items activos que coinciden (con normalización de género)
        activos = [
            item for item in items
            if item.get("activo", True)
            and _match(search_value, str(item.get(search_field, "")))
        ]

        if not activos:
            logger.info("[VectorSearchNode] Sin match para %s='%s'", search_field, search_value)
            state.vars[search_field] = search_value
            # Dejar en contexto los ítems activos disponibles para que el LLM
            # pueda responder "qué tienen" cuando no hay búsqueda específica.
            disponibles = [
                item for item in items
                if item.get("activo", True)
            ]
            if disponibles:
                state.context = json.dumps(disponibles, ensure_ascii=False)
            return state

        item = activos[0]
        logger.info("[VectorSearchNode] Match: %s='%s' → %s", search_field, search_value, item)

        # Poblar state.vars con todas las keys del ítem
        for key, value in item.items():
            if key != "activo":
                state.vars[key] = value

        # Aseguramos que el search_field esté en vars con el valor normalizado del LLM
        state.vars[search_field] = search_value

        # text para state.context: serialización del ítem
        state.context = json.dumps(item, ensure_ascii=False)
        logger.info("[VectorSearchNode] vars: %s", list(item.keys()))
        return state

    # ── Modo registry ──────────────────────────────────────────────────────────

    async def _run_registry(self, state: FlowState) -> FlowState:
        collection = self.config.get("collection")
        if not collection:
            logger.warning("[VectorSearchNode] No se especificó 'collection'")
            return state

        query_field  = self.config.get("query_field", "message")
        output_field = self.config.get("output_field", "context")
        top_k        = self.config.get("top_k", 3)

        query = self._get_field(state, query_field)
        if not query:
            logger.warning("[VectorSearchNode] Query vacía del campo '%s'", query_field)
            return state

        query = interpolate(query, state)

        try:
            from graphs.collections import get_handler
            handler = get_handler(collection)
            if not handler:
                logger.warning("[VectorSearchNode] Handler no registrado para '%s'", collection)
                return state

            result = await handler(query, top_k, state.empresa_id)
            if not result:
                logger.info("[VectorSearchNode] Sin resultados para '%s'", collection)
                return state

            for key, value in result.items():
                state.vars[key] = value

            text = result.get("text") or result.get("mensaje") or json.dumps(result, ensure_ascii=False)
            if output_field == "context":
                state.context = text
            elif output_field == "query":
                state.query = text

            logger.info("[VectorSearchNode] Registry '%s' → vars: %s", collection, list(result.keys()))
        except Exception as e:
            logger.error("[VectorSearchNode] Error en collection '%s': %s", collection, e)

        return state

    def _get_field(self, state: FlowState, field: str) -> str:
        if field == "message": return state.message
        if field == "query":   return state.query
        if field == "context": return state.context
        return ""

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "mode": {
                "type":    "select",
                "label":   "Modo de búsqueda",
                "default": "registry",
                "options": [
                    {"value": "registry", "label": "Colección registrada"},
                    {"value": "inline",   "label": "Lista editable (inline)"},
                ],
            },
            # Modo registry
            "collection": {
                "type":    "string",
                "label":   "Colección",
                "default": "",
                "hint":    "ej: luganense_oficios",
                "show_if": {"mode": "registry"},
            },
            "query_field": {
                "type":    "select",
                "label":   "Fuente del query",
                "default": "message",
                "options": ["message", "query", "context"],
                "show_if": {"mode": "registry"},
            },
            "output_field": {
                "type":    "select",
                "label":   "Destino del resultado",
                "default": "context",
                "options": ["context", "query"],
                "show_if": {"mode": "registry"},
            },
            "top_k": {
                "type":    "float",
                "label":   "Cantidad de resultados",
                "default": 3,
                "show_if": {"mode": "registry"},
            },
            # Modo inline
            "search_field": {
                "type":    "string",
                "label":   "Campo de búsqueda",
                "default": "oficio",
                "hint":    "El campo del ítem por el que se busca (ej: oficio, categoria)",
                "show_if": {"mode": "inline"},
            },
            "items": {
                "type":    "json",
                "label":   "Ítems",
                "default": [],
                "hint":    'Array JSON. Cada ítem debe tener el campo de búsqueda y "activo": true/false.',
                "show_if": {"mode": "inline"},
            },
        }
