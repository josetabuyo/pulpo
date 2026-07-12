"""
FetchHttpNode — hace un GET HTTP a una URL externa y guarda el resultado en
state.data["context"] (y opcionalmente extrae el primer resultado a variables).

Config:
  url:       str — URL para el GET. Soporta los mismos templates que el resto de
                    los nodos (ver interpolate() en base.py): {{conversation.last}},
                    {{necesidad}}, {{contact_name}}, etc. Además, {{query}} tiene
                    fallback propio: state.data["query"] → state.data["necesidad"] →
                    último mensaje de la conversación — url-encodeado.
                    Ej: https://api.ejemplo.com/buscar?q={{query}}
  extract:   str — "text" | "json" | "html"
  extract_first_result_to_vars: bool — si extract="json" y la respuesta tiene
                    forma {"results": [...]}, vuelca el primer resultado a state.data
"""
import logging
from urllib.parse import quote

from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)

# Claves con semántica propia del engine — no deben ser pisadas por datos externos
_RESERVED_KEYS = frozenset({"route", "reply", "context", "query", "fb_posts", "source_urls", "_node_errors"})


class FetchHttpNode(BaseNode):
    label = "Fetch HTTP"
    color = "#1e40af"
    description = "Hace un GET a una URL externa y guarda la respuesta como contexto."

    async def run(self, state: FlowState) -> FlowState:
        url                   = self.config.get("url", "")
        extract               = self.config.get("extract", "text")
        extract_first_to_vars = self.config.get("extract_first_result_to_vars", False)
        if not url:
            logger.warning("[FetchHttpNode] sin url configurada")
            return state

        # {{query}} tiene fallback propio (más limpio para buscar que el mensaje crudo):
        # state.data["query"] → state.data["necesidad"] → último mensaje de la conversación.
        conversation = state.data.get("conversation") or []
        last_message = conversation[-1].get("content", "") if conversation else (state.message or "")
        query_value = state.data.get("query") or state.data.get("necesidad") or last_message or ""
        url = url.replace("{{query}}", quote(str(query_value), safe=""))
        url = url.replace("{{message}}", quote(str(last_message), safe=""))
        # Sintaxis legacy de una sola llave (flows viejos) — mismo fallback.
        url = url.replace("{query}", quote(str(query_value), safe=""))
        url = url.replace("{message}", quote(str(last_message), safe=""))

        # Cualquier otro placeholder ({{necesidad}}, {{contact_name}}, {{conversation...}}, etc.)
        url = interpolate(url, state)

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                if extract in ("json", "html"):
                    state.data["context"] = resp.text
                else:
                    # extraer texto plano básico
                    import re
                    text = re.sub(r"<[^>]+>", " ", resp.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    state.data["context"] = text[:5000]
            logger.info("[FetchHttpNode] %s: %d chars", url[:60], len(state.data.get("context", "")))

            if extract_first_to_vars and extract == "json" and state.data.get("context"):
                self._extract_first_to_vars(state)
        except Exception as e:
            logger.error("[FetchHttpNode] Error HTTP GET %s: %s", url, e)

        return state

    def _extract_first_to_vars(self, state: FlowState) -> None:
        import json as _json
        try:
            data = _json.loads(state.data["context"])
            results = data.get("results") if isinstance(data, dict) else None
            if not results or not isinstance(results, list) or not results[0]:
                return
            for k, v in results[0].items():
                if k in _RESERVED_KEYS:
                    logger.warning("[FetchHttpNode] campo externo '%s' colisiona con clave reservada — ignorado", k)
                    continue
                state.data[k] = v
            # Expandir contactos: [{tipo, valor}] a vars planos por tipo
            contactos = results[0].get("contactos")
            if isinstance(contactos, list):
                for c in contactos:
                    tipo = c.get("tipo") if isinstance(c, dict) else None
                    valor = c.get("valor") if isinstance(c, dict) else None
                    if tipo and valor and tipo not in _RESERVED_KEYS:
                        state.data[tipo] = valor
            logger.info("[FetchHttpNode] extract_first_to_vars: %d campos → vars", len(results[0]))
        except Exception as ex:
            logger.warning("[FetchHttpNode] extract_first_to_vars falló: %s", ex)

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "url": {
                "type":    "string",
                "label":   "URL",
                "default": "",
                "hint":    "https://api.ejemplo.com/buscar?q={{query}} — soporta {{query}}, {{conversation.last}} y cualquier variable del flow",
            },
            "extract": {
                "type":    "select",
                "label":   "Formato de respuesta",
                "default": "text",
                "options": ["text", "json", "html"],
            },
            "extract_first_result_to_vars": {
                "type":    "bool",
                "label":   "Volcar primer resultado a variables",
                "default": False,
                "hint":    "Si la respuesta JSON tiene forma {\"results\": [...]}, copia el primer item a state.data",
            },
        }
