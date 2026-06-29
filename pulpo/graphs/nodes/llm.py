"""
LLMNode — llama a un LLM con prompt configurable.

Config:
  prompt:          str   — system prompt
  model:           str   — modelo a usar (best:*, ollama/*, groq/*, o legacy)
  router_strategy: str   — "local-first" | "cloud-first" (solo aplica a best:*)
  temperature:     float — temperatura (default: 0.3)
  output:          str   — dónde guardar la respuesta:
                            "reply"   → state.reply (responde al usuario)
                            "context" → state.context (para el siguiente nodo)
                            "query"   → state.query (para fetch/search)
  json_output:     bool  — pedir respuesta JSON (para nodos que devuelven estructurado)
  json_reply_key:  str   — clave del JSON que contiene el reply (default: "reply")
  json_route_key:  str   — clave del JSON que contiene el route (opcional)
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


def parse_model_strategy(raw: str, config: dict) -> tuple[str, str]:
    """Parse 'best:cat|strategy' → (model, router_strategy). Backward-compat with old configs."""
    if "|" in raw:
        model, alias = raw.split("|", 1)
        return model, _STRATEGY_MAP.get(alias, "local-first")
    return raw, config.get("router_strategy", "local-first")


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
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            from langchain_groq import ChatGroq
            groq_extra = {"max_tokens": max_tokens} if max_tokens is not None else {}
            groq_fallback = ChatGroq(
                model="llama-3.3-70b-versatile",
                api_key=groq_key,
                temperature=temperature,
                **groq_extra,
            )
            return primary.with_fallbacks([groq_fallback])
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
        model, router_strategy = parse_model_strategy(raw_model, self.config)

        # Interpolar placeholders en el prompt y construir system.
        # Compat: si el prompt no menciona {{context}} pero hay contexto, se agrega al final.
        system = interpolate(prompt, state)
        if state.context and "{{context}}" not in prompt:
            system += f"\n\nContexto:\n{state.context}"

        try:
            llm = _build_llm(model, temperature, json_out, router_strategy)

            result = await llm.ainvoke([
                {"role": "system", "content": system},
                {"role": "user",   "content": state.message},
            ])
            content = result.content

            if json_out:
                data = json.loads(content)
                text = data.get(reply_key, "")
                if route_key and data.get(route_key):
                    state.route = str(data[route_key])
            else:
                text = content

            if output == "reply":
                state.reply = text
            elif output == "context":
                state.context = text
            elif output == "query":
                state.query = text.strip()

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
            "output":          {"type": "select",   "label": "Destino de la salida",   "default": "reply",
                                "hint": "reply = responde al usuario · context = pasa al siguiente nodo · query = para búsqueda/fetch",
                                "options": [
                                    {"value": "reply",   "label": "reply — responde al usuario"},
                                    {"value": "context", "label": "context — pasa al siguiente nodo"},
                                    {"value": "query",   "label": "query — para búsqueda vectorial / fetch"},
                                ]},
            "json_output":     {"type": "bool",     "label": "Respuesta JSON",         "default": False},
            "json_reply_key":  {"type": "string",   "label": "Clave JSON del reply",   "default": "reply",
                                "hint": "Clave dentro del JSON que contiene el texto a responder",
                                "show_if": {"json_output": True}},
        }
