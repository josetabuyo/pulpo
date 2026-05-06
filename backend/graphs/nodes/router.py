"""
RouterNode — clasificador LLM que setea state.route.

El engine sigue solo los edges con label == state.route.

Config:
  prompt:         str   — system prompt para el clasificador
  routes:         list  — valores válidos (ej: ["noticias", "oficio", "auspiciante"])
  fallback:       str   — route por defecto si el LLM no responde algo válido
  model:          str   — modelo Groq (default: llama-3.3-70b-versatile)
  context_source: str   — qué parte del state inyectar al mensaje del usuario:
                          "none" (default) | "vars" | "context" | "vars+context"
"""
import json
import logging
import os
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


def _build_user_message(state: FlowState, context_source: str) -> str:
    parts = [f"Mensaje: {state.message}"]
    if "vars" in context_source and state.vars:
        parts.append(f"Variables: {json.dumps(state.vars, ensure_ascii=False)}")
    if "context" in context_source and state.context:
        parts.append(f"Contexto: {state.context}")
    return "\n\n".join(parts)


class RouterNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        prompt         = self.config.get("prompt", "")
        routes         = self.config.get("routes", [])
        fallback       = self.config.get("fallback", routes[0] if routes else "")
        model          = self.config.get("model", "llama-3.3-70b-versatile")
        context_source = self.config.get("context_source", "none")

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or not prompt:
            logger.warning("[RouterNode] Sin GROQ_API_KEY o prompt — usando fallback '%s'", fallback)
            state.route = fallback
            return state

        user_message = _build_user_message(state, context_source)

        try:
            from langchain_groq import ChatGroq
            llm = ChatGroq(model=model, api_key=api_key, max_tokens=10, temperature=0)
            result = await llm.ainvoke([
                {"role": "system", "content": prompt},
                {"role": "user",   "content": user_message},
            ])
            route = result.content.strip().lower()
            if routes and route not in routes:
                logger.info("[RouterNode] respuesta '%s' no válida — usando fallback '%s'", route, fallback)
                route = fallback
            logger.info("[RouterNode] route → '%s' | msg: %.60s | ctx: %s", route, state.message, context_source)
            state.route = route
        except Exception as e:
            logger.error("[RouterNode] Error: %s — fallback '%s'", e, fallback)
            state.route = fallback

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "prompt":   {"type": "textarea", "label": "Prompt del clasificador", "default": "", "rows": 7},
            "routes":   {"type": "list",     "label": "Rutas válidas",           "default": [], "hint": "Separadas por coma — ej: noticias,oficio,auspiciante"},
            "fallback": {"type": "string",   "label": "Ruta por defecto",        "default": "", "hint": "Si el LLM responde algo inválido"},
            "model":    {"type": "string",   "label": "Modelo",                  "default": "llama-3.3-70b-versatile"},
            "context_source": {
                "type":    "select",
                "label":   "Contexto adicional al mensaje",
                "default": "none",
                "options": [
                    {"value": "none",         "label": "Solo el mensaje"},
                    {"value": "vars",         "label": "Mensaje + variables"},
                    {"value": "context",      "label": "Mensaje + contexto"},
                    {"value": "vars+context", "label": "Mensaje + variables + contexto"},
                ],
            },
        }
