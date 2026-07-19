"""
LLMNode — llama a un LLM con prompt configurable.

El prompt (system) se interpola normalmente ({{conversation}}, {{conversation.last}}, {{context}},
etc. — ver interpolate() en base.py). No se manda nada de más por default: si el nodo necesita
el historial de la conversación o el contexto de un fetch previo, tiene que pedirlo explícito
con esos placeholders en el prompt. El único turno de usuario que se manda siempre es el mensaje
entrante actual (state.message) — evita duplicar tokens mandando la conversación dos veces
(una como texto interpolado, otra como turnos user/assistant separados).

Config:
  prompt:          str   — system prompt
  model:           str   — modelo a usar (best:cat|strategy, ollama/*, groq/*, o legacy)
  temperature:     float — temperatura (default: 0.3)
  output:          str   — clave de state.data donde guardar la respuesta (libre).
                            Convenciones usadas por otros nodos:
                            "reply"   → responde al usuario
                            "context" → pasa al siguiente nodo
                            "query"   → para búsqueda vectorial / fetch
                            Cualquier otro nombre es una clave de negocio válida.
  json_output:     bool  — pedir respuesta JSON (para nodos que devuelven estructurado)
  json_reply_key:  str   — clave del JSON que contiene el reply (default: "reply")
  json_route_key:  str   — clave del JSON que contiene el route (opcional)
  output_as_list:  bool  — en vez de guardar la respuesta como texto plano, la parte
                            por líneas y guarda una lista de {"text": línea} en
                            state.data[output]. Pensado para prompts que piden "una
                            búsqueda por línea" y alimentan un FetchHttpNode con
                            array_input — cada item queda referenciable como
                            {{item.text}} en la URL del fetch.
"""
import json
import logging
import os
import re
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)

_MAX_EMPTY_RETRIES = 1  # 1 reintento extra (2 intentos totales) si el LLM devuelve contenido vacío

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think_blocks(content: str) -> str:
    """
    Algunos modelos de razonamiento servidos por el router (ej. variantes
    DeepSeek R1) devuelven el chain-of-thought crudo como `<think>...</think>`
    dentro de `result.content` en vez de separarlo en `reasoning_content` —
    bug real encontrado 2026-07-16: el nodo "elegir_rubro" del flow de
    Luganense devolvió el bloque de razonamiento completo como si fuera la
    respuesta final, y ese texto terminó interpolado en la URL de
    `buscar_servicio` (`{{rubro_elegido}}`), rompiendo el fetch real con un
    "Invalid non-printable ASCII character in URL". Se filtra acá, en el
    único lugar donde se extrae el contenido del LLM, así ningún nodo aguas
    abajo puede volver a filtrar esto.
    """
    return _THINK_BLOCK_RE.sub("", content).strip()


def _record_llm_error(state: FlowState, output: str, detail: str) -> None:
    """
    Análogo a `_record_fetch_error` en fetch_http.py — antes, un LLM que
    respondía contenido vacío (sin levantar excepción; distinto del caso ya
    manejado por el try/except de más abajo) quedaba invisible: el output
    caía en `""` en silencio, indistinguible de una decisión legítima del
    modelo (ej. un LLM que a propósito devuelve string vacío). Bug real
    encontrado 2026-07-13: "Obtener necesidad" y otros nodos LLM del flow de
    Luganense devolvían vacío de forma intermitente (~1 de cada 8 llamadas en
    una muestra directa), haciendo que el flow quedara pidiendo aclaración en
    loop sin ningún error visible en el log.
    """
    state.data.setdefault("_llm_errors", []).append({"output": output, "error": detail})

_ROUTER_URL = os.getenv("MODEL_ROUTER_URL", "http://localhost:9002")

_CATEGORIES = [
    "instruction", "reasoning", "coding", "code_debug",
    "math", "summarization", "multilingual", "context",
]

_STRATEGIES = [
    ("local",       "local"),
    ("local-first", "local → cloud"),
    ("cloud-first", "cloud → local"),
    ("cloud",       "cloud"),
]

MODEL_OPTIONS = [
    {"value": f"best:{cat}|{strat}", "label": f"best:{cat} — {label}"}
    for cat in _CATEGORIES
    for strat, label in _STRATEGIES
]

_STRATEGY_MAP = {
    "local":       "local-only",
    "local-first": "local-first",
    "cloud-first": "cloud-first",
    "cloud":       "cloud-best-with-local-fallback",
}


def parse_model_strategy(raw: str) -> tuple[str, str]:
    """Parse 'best:cat|strategy' → (model, router_strategy)."""
    if "|" in raw:
        model, alias = raw.split("|", 1)
        return model, _STRATEGY_MAP.get(alias, "local-first")
    return raw, "local-first"


def _build_llm(model: str, temperature: float, json_out: bool, router_strategy: str, max_tokens: int | None = None):
    """Construye el LLM correcto según el formato del model string."""
    extra: dict = {}
    if json_out:
        extra["model_kwargs"] = {"response_format": {"type": "json_object"}}
    if max_tokens is not None:
        extra["max_tokens"] = max_tokens

    from langchain_openai import ChatOpenAI

    if model.startswith("best:"):
        if router_strategy == "local-only":
            return ChatOpenAI(
                model=model,
                base_url=f"{_ROUTER_URL}/local/v1",
                api_key="router",
                temperature=temperature,
                **extra,
            )

        if router_strategy == "cloud-best-with-local-fallback":
            primary = ChatOpenAI(
                model=model,
                base_url=f"{_ROUTER_URL}/cloud/v1",
                api_key="router",
                temperature=temperature,
                **extra,
            )
            local_fallback = ChatOpenAI(
                model=model,
                base_url=f"{_ROUTER_URL}/local/v1",
                api_key="router",
                temperature=temperature,
                **extra,
            )
            return primary.with_fallbacks([local_fallback])

        # local-first / cloud-first — endpoint híbrido /v1
        primary = ChatOpenAI(
            model=model,
            base_url=f"{_ROUTER_URL}/v1",
            api_key="router",
            temperature=temperature,
            default_headers={"X-Router-Strategy": router_strategy},
            **extra,
        )
        return primary

    if model.startswith("ollama/"):
        return ChatOpenAI(
            model=model,
            base_url=f"{_ROUTER_URL}/local/v1",
            api_key="router",
            temperature=temperature,
            **extra,
        )

    if model.startswith("groq/"):
        return ChatOpenAI(
            model=model,
            base_url=f"{_ROUTER_URL}/cloud/v1",
            api_key="router",
            temperature=temperature,
            **extra,
        )

    if model.startswith("local:"):
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return ChatOpenAI(
            model=model.removeprefix("local:"),
            base_url=ollama_url,
            api_key="ollama",
            temperature=temperature,
            **extra,
        )

    # Legacy: Groq directo
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("Sin GROQ_API_KEY")
    from langchain_groq import ChatGroq
    return ChatGroq(model=model, api_key=api_key, temperature=temperature, **extra)


class LLMNode(BaseNode):
    label = "Respuesta LLM"
    color = "#6b21a8"
    description = "Genera una respuesta usando un modelo de lenguaje."

    async def run(self, state: FlowState) -> FlowState:
        if state.from_delta_sync:
            return state

        prompt      = self.config.get("prompt", "")
        raw_model   = self.config.get("model", "best:instruction|local-first")
        temperature = float(self.config.get("temperature", 0.3))
        output      = self.config.get("output", "reply")
        json_out    = bool(self.config.get("json_output", False))
        reply_key   = self.config.get("json_reply_key", "reply")
        route_key   = self.config.get("json_route_key", "")
        as_list     = bool(self.config.get("output_as_list", False))
        max_tokens  = self.config.get("max_tokens") or None
        model, router_strategy = parse_model_strategy(raw_model)

        # Interpolar placeholders en el prompt y construir system. Nada se agrega de más:
        # si el prompt necesita {{context}} o {{conversation}}, tiene que pedirlo explícito
        # (ver interpolate() en base.py) — evita mandar contexto/historial no solicitado.
        system = interpolate(prompt, state)

        try:
            llm = _build_llm(model, temperature, json_out, router_strategy, max_tokens)

            # Un solo turno de usuario: el mensaje entrante actual. El historial completo
            # de la conversación, si el nodo lo necesita, ya quedó embebido como texto en
            # `system` vía {{conversation}} — no se duplica mandándolo también como
            # turnos user/assistant separados.
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": state.message},
            ]

            # Reintenta si el modelo devuelve contenido vacío sin levantar excepción
            # (bug real: intermitente en la cascada cloud-first, ver _record_llm_error) —
            # antes esto se guardaba tal cual, indistinguible de una decisión legítima
            # del modelo, y dejaba el flow pidiendo aclaración en loop sin ningún error
            # visible en el log.
            attempts = 0
            text = ""
            while True:
                attempts += 1
                result = await llm.ainvoke(messages)
                content = _strip_think_blocks(result.content or "")

                if json_out:
                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        parsed = {}
                    text = parsed.get(reply_key, "") if isinstance(parsed, dict) else ""
                    if route_key and isinstance(parsed, dict) and parsed.get(route_key):
                        state.data["route"] = str(parsed[route_key])
                else:
                    text = content

                if text.strip():
                    break
                if attempts > _MAX_EMPTY_RETRIES:
                    detail = f"LLM devolvió contenido vacío tras {attempts} intento(s)"
                    logger.error("[LLMNode] %s (output=%s)", detail, output)
                    _record_llm_error(state, output, detail)
                    break
                logger.warning("[LLMNode] contenido vacío en intento %d, reintentando (output=%s)", attempts, output)

            # El nodo pidió cloud (cloud-first / cloud-best-with-local-fallback) pero el
            # router terminó sirviendo un modelo local — significa que TODOS los
            # proveedores cloud de la cascada fallaron. No es un error del flow (el nodo
            # igual respondió), pero es una señal de degradación del lado del router que
            # conviene ver, no solo inferir de la latencia. Tag greppable para Monitor.
            served_model = result.response_metadata.get("model_name", "")
            if router_strategy in ("cloud-first", "cloud-best-with-local-fallback") and served_model.startswith("ollama/"):
                logger.warning(
                    "[LLMNode] ROUTER_FALLBACK_LOCAL output=%s configured_model=%s router_strategy=%s served_model=%s",
                    output, model, router_strategy, served_model,
                )

            if as_list:
                items = [{"text": line.strip()} for line in text.splitlines() if line.strip()]
                state.data[output] = items
                logger.info("[LLMNode] output=%s items=%d", output, len(items))
            else:
                state.data[output] = text.strip()
                logger.info("[LLMNode] output=%s len=%d", output, len(text))

        except Exception as e:
            logger.error("[LLMNode] Error: %s", e)

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "prompt":          {"type": "textarea", "label": "System prompt",          "default": "", "rows": 8},
            "model":       {"type": "select", "label": "Modelo", "default": "best:instruction|local-first",
                            "options": MODEL_OPTIONS},
            "temperature":     {"type": "float",    "label": "Temperatura",            "default": 0.3},
            "output":          {"type": "string",   "label": "Destino de la salida",   "default": "reply",
                                "hint": "Clave de state.data donde se guarda la respuesta. "
                                        "reply = responde al usuario · context = pasa al siguiente nodo · "
                                        "query = para búsqueda vectorial / fetch · o cualquier nombre custom "
                                        "(ej: necesidad, mensaje_pedido_necesidad)"},
            "json_output":     {"type": "bool",     "label": "Respuesta JSON",         "default": False},
            "json_reply_key":  {"type": "string",   "label": "Clave JSON del reply",   "default": "reply",
                                "hint": "Clave dentro del JSON que contiene el texto a responder",
                                "show_if": {"json_output": True}},
            "output_as_list":  {"type": "bool",     "label": "Salida como lista (una por línea)", "default": False,
                                "hint": "Parte la respuesta por líneas y guarda [{\"text\": línea}, ...] "
                                        "en vez de texto plano. Para alimentar un FetchHttpNode con "
                                        "array_input, referenciando {{item.text}} en la URL."},
            "max_tokens":      {"type": "int",      "label": "Máximo de tokens (opcional)", "default": None,
                                "hint": "Vacío = default del router de modelos. Subilo si las respuestas "
                                        "se cortan a mitad de frase (pasa seguido con prompts que piden "
                                        "citar URLs largas + una línea de cierre)."},
        }
