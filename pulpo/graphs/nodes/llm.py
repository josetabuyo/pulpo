"""
LLMNode — llama a un LLM con prompt configurable.

El prompt (system) se interpola normalmente ({{conversation}}, {{conversation.last}}, etc.
— ver interpolate() en base.py). Además, los turnos de state.data["conversation"] se mandan
completos como mensajes user/assistant (no solo el último), para que el modelo tenga memoria
real de la conversación.

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
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)

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

        # Interpolar placeholders en el prompt y construir system.
        # Compat: si el prompt no menciona {{context}} pero hay contexto, se agrega al final.
        system = interpolate(prompt, state)
        context = state.data.get("context", "")
        if context and "{{context}}" not in prompt:
            system += f"\n\nContexto:\n{context}"

        try:
            llm = _build_llm(model, temperature, json_out, router_strategy, max_tokens)

            # El historial de turnos (user/bot_reply) de esta ejecución de flow
            # se manda completo como user/assistant — le da memoria real al LLM
            # en vez de solo el último mensaje entrante.
            messages = [{"role": "system", "content": system}]
            conversation = state.data.get("conversation") or []
            if conversation:
                role_by_origin = {"user": "user", "bot_reply": "assistant"}
                messages += [
                    {"role": role_by_origin.get(entry.get("origin"), "user"), "content": entry.get("content", "")}
                    for entry in conversation
                ]
            else:
                messages.append({"role": "user", "content": state.message})

            result = await llm.ainvoke(messages)
            content = result.content

            if json_out:
                parsed = json.loads(content)
                text = parsed.get(reply_key, "")
                if route_key and parsed.get(route_key):
                    state.data["route"] = str(parsed[route_key])
            else:
                text = content

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
