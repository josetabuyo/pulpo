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
  extract_fields: dict[str, str] — solo con extract="json" y SIN array_input (un
                      único GET, un único objeto — con múltiples respuestas la ruta
                      "cuál es la primera válida" ya no es un mapeo 1:1 inequívoco).
                      Cada entrada {clave_de_salida: "ruta.anidada.al.campo"} parsea
                      el JSON de la respuesta y escribe ese valor plano directo en
                      state.data[clave_de_salida] — sin pasar por un LLM. Pensado para
                      APIs que devuelven UN solo resultado ya resuelto del lado del
                      proveedor (ej. `GET /candidato?q=...` → {"candidato": {"nombre":
                      ..., "contact_id": ...}}), evitando que un LLM tenga que "elegir"
                      o inventar un dato que el proveedor ya entregó resuelto.
                      Ruta inexistente o valor `null` → esa clave NO se escribe en
                      absoluto (se deja sin resolver, nunca un string vacío que
                      esconda el "no hay dato" — mismo criterio que interpolate() en
                      base.py). El output crudo (`output`) se sigue guardando igual,
                      así los prompts existentes que ya lo referencian no se rompen.
"""
import json
import logging
import re
from urllib.parse import quote

from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)

_MAX_ARRAY_ITEMS = 10

_ITEM_FIELD_RE = re.compile(r"\{\{item\.([a-zA-Z0-9_]+)\}\}")
_ITEM_RE = re.compile(r"\{\{item\}\}")
_UNRESOLVED_TEMPLATE_RE = re.compile(r"\{\{.*?\}\}")


def _record_fetch_error(state: FlowState, url: str, error: str, status_code: int | None = None) -> None:
    """
    Registra un fallo de fetch en `state.data["_fetch_errors"]` — a diferencia
    de `_node_errors` (compiler.py, solo se llena si el nodo LEVANTA una
    excepción), FetchHttpNode nunca deja que un fetch roto interrumpa el flow
    (ver docstring del módulo), así que sin esto un 404 o un placeholder
    `{{...}}` sin resolver en la URL quedaban invisibles para cualquier test
    que solo mirara `output_state`/reply — el output simplemente quedaba en
    None, indistinguible de "0 resultados reales".
    """
    state.data.setdefault("_fetch_errors", []).append({
        "url": url, "status_code": status_code, "error": error,
    })


_SENTINEL = object()


def _resolve_json_path(parsed, path: str):
    """Traversa `parsed` (dict/list ya deserializado) siguiendo `path`
    ("candidato.nombre", "resultados.0.nombre"). Devuelve `_SENTINEL` si
    cualquier tramo no existe — nunca levanta, nunca confunde "no encontrado"
    con un valor real (incluido `None`, que sí es un resultado válido a
    devolver tal cual si el campo existe pero es null)."""
    current = parsed
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return _SENTINEL
            current = current[part]
        elif isinstance(current, list):
            if not part.lstrip("-").isdigit():
                return _SENTINEL
            idx = int(part)
            if idx < -len(current) or idx >= len(current):
                return _SENTINEL
            current = current[idx]
        else:
            return _SENTINEL
    return current


def _apply_extract_fields(state: FlowState, raw: str | None, extract_fields: dict) -> None:
    if not raw:
        return
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("[FetchHttpNode] extract_fields: respuesta no es JSON válido, se omite")
        return
    for key, path in extract_fields.items():
        value = _resolve_json_path(parsed, path)
        if value is _SENTINEL or value is None:
            continue  # sin dato real — no se escribe la clave (ver docstring del módulo)
        state.data[key] = value


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
                        results.append(await self._get(client, item_url, extract, state))
                    state.data[output] = results
                    logger.info(
                        "[FetchHttpNode] array_input='%s' → %d llamados → %s",
                        array_input, len(results), output,
                    )
                else:
                    url = self._resolve_url(url_template, state)
                    raw = await self._get(client, url, extract, state)
                    state.data[output] = raw
                    logger.info("[FetchHttpNode] %s: %d chars → %s", url[:60], len(raw or ""), output)
                    extract_fields = self.config.get("extract_fields") or {}
                    if extract_fields and extract == "json":
                        _apply_extract_fields(state, raw, extract_fields)
        except Exception as e:
            logger.error("[FetchHttpNode] Error HTTP GET: %s", e)
            _record_fetch_error(state, url_template, str(e))

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

    async def _get(self, client, url: str, extract: str, state: FlowState) -> str | None:
        if _UNRESOLVED_TEMPLATE_RE.search(url):
            logger.error("[FetchHttpNode] URL con placeholder {{...}} sin resolver: %s", url)
            _record_fetch_error(state, url, "unresolved {{...}} placeholder in URL")
            return None
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
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            logger.error("[FetchHttpNode] Error HTTP GET %s: %s", url, e)
            _record_fetch_error(state, url, str(e), status_code)
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
            "extract_fields": {
                "type":    "json",
                "label":   "Extraer campos del JSON (opcional, sin array_input)",
                "default": {},
                "hint":    "Solo con formato 'json' y sin array_input. Mapeo "
                           "{clave_de_salida: \"ruta.anidada.al.campo\"} — ej. "
                           "{\"servicio\": \"candidato.nombre\", \"servicio_contact_id\": "
                           "\"candidato.contact_id\"}. Escribe cada valor directo en state.data, "
                           "sin pasar por un LLM. Ruta inexistente o null → no escribe esa clave.",
            },
        }
