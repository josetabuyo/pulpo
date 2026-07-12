"""
FetchHttpNode — hace uno o más GET HTTP a una URL externa y guarda la
respuesta cruda en state.data[output].

Config:
  url:         str — URL para el GET. Soporta los mismos templates que el resto de
                      los nodos (ver interpolate() en base.py): {{conversation.last}},
                      {{necesidad}}, {{contact_name}}, etc. Además, {{query}} tiene
                      fallback propio: state.data["query"] → state.data["necesidad"] →
                      último mensaje de la conversación — url-encodeado.
                      Ej: https://api.ejemplo.com/buscar?q={{query}}
  extract:     str — "text" | "json" | "html"
  output:      str — clave de state.data donde se guarda la respuesta cruda
                      (default: "context"). Cualquier nombre custom permite leerla
                      después en otro nodo con {{ese_nombre}}, sin que la pise el
                      próximo Fetch HTTP del flow. El filtrado (ej: quedarse con el
                      primer resultado de un array) es responsabilidad de quien lee
                      esa variable (un LLM con json_output, o un template puntual),
                      no de este nodo.
  array_input: str — nombre de una variable de state.data que contiene una lista
                      (ej. generada por un LLMNode con output_as_list). Si está
                      seteada y la variable existe y no está vacía, se hace un GET
                      por cada item de la lista en vez de uno solo, y state.data[output]
                      queda como una lista de respuestas (mismo orden que los items,
                      None en la posición de un item que falló).
                      La URL puede referenciar campos del item con {{item.campo}}
                      (ej. {{item.text}} si el item es {"text": "..."}), o {{item}}
                      si el item es un valor plano (no dict). Cualquier otro
                      placeholder del flow se resuelve igual que en modo simple.
                      Vacío (default) = comportamiento de un solo GET, sin cambios.
"""
import logging
import re
from urllib.parse import quote

from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)

_MAX_ARRAY_ITEMS = 10

_ITEM_FIELD_RE = re.compile(r"\{\{item\.([a-zA-Z0-9_]+)\}\}")
_ITEM_RE = re.compile(r"\{\{item\}\}")


def _fill_item_template(url_template: str, item) -> str:
    def repl_field(m):
        value = item.get(m.group(1), "") if isinstance(item, dict) else ""
        return quote(str(value), safe="")

    url = _ITEM_FIELD_RE.sub(repl_field, url_template)
    if not isinstance(item, dict):
        url = _ITEM_RE.sub(quote(str(item), safe=""), url)
    return url


class FetchHttpNode(BaseNode):
    label = "Fetch HTTP"
    color = "#1e40af"
    description = "Hace uno o más GET a una URL externa y guarda la respuesta como contexto."

    async def run(self, state: FlowState) -> FlowState:
        url_template = self.config.get("url", "")
        extract      = self.config.get("extract", "text")
        output       = self.config.get("output", "context") or "context"
        array_input  = self.config.get("array_input", "").strip()
        if not url_template:
            logger.warning("[FetchHttpNode] sin url configurada")
            return state

        items = state.data.get(array_input) if array_input else None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                if array_input and isinstance(items, list) and items:
                    if len(items) > _MAX_ARRAY_ITEMS:
                        logger.warning(
                            "[FetchHttpNode] array_input '%s' tiene %d items — truncado a %d",
                            array_input, len(items), _MAX_ARRAY_ITEMS,
                        )
                    results = []
                    for item in items[:_MAX_ARRAY_ITEMS]:
                        item_url = self._resolve_url(_fill_item_template(url_template, item), state)
                        results.append(await self._get(client, item_url, extract))
                    state.data[output] = results
                    logger.info(
                        "[FetchHttpNode] array_input='%s' → %d llamados → %s",
                        array_input, len(results), output,
                    )
                else:
                    url = self._resolve_url(url_template, state)
                    state.data[output] = await self._get(client, url, extract)
                    logger.info("[FetchHttpNode] %s: %d chars → %s", url[:60], len(state.data.get(output) or ""), output)
        except Exception as e:
            logger.error("[FetchHttpNode] Error HTTP GET: %s", e)

        return state

    def _resolve_url(self, url: str, state: FlowState) -> str:
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
        return interpolate(url, state)

    async def _get(self, client, url: str, extract: str) -> str | None:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            if extract in ("json", "html"):
                return resp.text
            # extraer texto plano básico
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:5000]
        except Exception as e:
            logger.error("[FetchHttpNode] Error HTTP GET %s: %s", url, e)
            return None

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "url": {
                "type":    "string",
                "label":   "URL",
                "default": "",
                "hint":    "https://api.ejemplo.com/buscar?q={{query}} — soporta {{query}}, {{conversation.last}}, "
                           "cualquier variable del flow, y {{item.campo}}/{{item}} si usás array_input",
            },
            "extract": {
                "type":    "select",
                "label":   "Formato de respuesta",
                "default": "text",
                "options": ["text", "json", "html"],
            },
            "output": {
                "type":    "string",
                "label":   "Variable de salida",
                "default": "context",
                "hint":    "Clave de state.data donde se guarda la respuesta. "
                           "context = default, pasa al siguiente nodo · o cualquier "
                           "nombre custom (ej: resultado_servicio) para leerla después "
                           "en otro nodo con {{resultado_servicio}} sin que la pise el "
                           "próximo Fetch HTTP del flow",
            },
            "array_input": {
                "type":    "string",
                "label":   "Variable con array de inputs (opcional)",
                "default": "",
                "hint":    "Nombre de una variable de state.data con una lista (ej. la que arma un "
                           "LLM con 'Salida como lista'). Si está seteada, se hace un GET por cada "
                           "item y output queda como lista de respuestas. Referenciá campos del item "
                           "en la URL con {{item.campo}} (o {{item}} si es un valor plano). "
                           "Vacío = un solo GET, como siempre.",
            },
        }
