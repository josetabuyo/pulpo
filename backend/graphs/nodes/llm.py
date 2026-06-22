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

_ROUTER_URL = os.getenv("MODEL_ROUTER_URL", "http://localhost:11435")

MODEL_OPTIONS = [
    # ── Híbrido — el router elige local o cloud según disponibilidad ──────────
    {"value": "best:instruction",    "label": "best:instruction — híbrido (recomendado)"},
    {"value": "best:summarization",  "label": "best:summarization — híbrido"},
    {"value": "best:reasoning",      "label": "best:reasoning — híbrido"},
    {"value": "best:multilingual",   "label": "best:multilingual — híbrido"},
    {"value": "best:context",        "label": "best:context — híbrido"},
    {"value": "best:coding",         "label": "best:coding — híbrido"},
    # ── Local (Ollama vía router) ─────────────────────────────────────────────
    {"value": "ollama/qwen2.5:7b",    "label": "qwen2.5:7b — local Ollama"},
    {"value": "ollama/deepseek-r1:8b","label": "deepseek-r1:8b — local Ollama (CoT lento)"},
    # ── Cloud Groq (vía router) ───────────────────────────────────────────────
    {"value": "groq/llama-3.3-70b-versatile", "label": "llama-3.3-70b-versatile (Groq)"},
    {"value": "groq/llama-3.1-8b-instant",    "label": "llama-3.1-8b-instant — rápido (Groq)"},
    # ── Legacy ───────────────────────────────────────────────────────────────
    {"value": "local:gemma4:e4b",            "label": "[legacy] Gemma 4 4B — Ollama directo"},
    {"value": "llama-3.3-70b-versatile",     "label": "[legacy] llama-3.3-70b-versatile (Groq directo)"},
    {"value": "llama-3.1-70b-versatile",     "label": "[legacy] llama-3.1-70b-versatile"},
    {"value": "llama-3.1-8b-instant",        "label": "[legacy] llama-3.1-8b-instant"},
    {"value": "llama3-70b-8192",             "label": "[legacy] llama3-70b-8192"},
    {"value": "llama3-8b-8192",              "label": "[legacy] llama3-8b-8192"},
    {"value": "mixtral-8x7b-32768",          "label": "[legacy] mixtral-8x7b-32768"},
    {"value": "gemma2-9b-it",                "label": "[legacy] gemma2-9b-it"},
]


def _build_llm(model: str, temperature: float, json_out: bool, router_strategy: str, max_tokens: int | None = None):
    """Construye el LLM correcto según el formato del model string."""
    extra: dict = {}
    if json_out:
        extra["model_kwargs"] = {"response_format": {"type": "json_object"}}
    if max_tokens is not None:
        extra["max_tokens"] = max_tokens

    from langchain_openai import ChatOpenAI

    if model.startswith("best:"):
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

        prompt          = self.config.get("prompt", "")
        model           = self.config.get("model", "best:instruction")
        temperature     = float(self.config.get("temperature", 0.3))
        output          = self.config.get("output", "reply")
        json_out        = bool(self.config.get("json_output", False))
        reply_key       = self.config.get("json_reply_key", "reply")
        route_key       = self.config.get("json_route_key", "")
        router_strategy = self.config.get("router_strategy", "local-first")

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
            "model":           {"type": "select",   "label": "Modelo",                 "default": "best:instruction",
                                "options": MODEL_OPTIONS},
            "router_strategy": {"type": "select",   "label": "Estrategia del router",  "default": "local-first",
                                "hint": "Aplica solo a modelos best:* — cuál priorizar cuando ambos están disponibles",
                                "options": [
                                    {"value": "local-first", "label": "local-first — Ollama primero, Groq como fallback"},
                                    {"value": "cloud-first", "label": "cloud-first — Groq primero, Ollama como fallback"},
                                ]},
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
