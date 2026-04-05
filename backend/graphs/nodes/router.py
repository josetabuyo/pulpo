"""
RouterNode — clasificador LLM que setea state.route.

El engine sigue solo los edges con label == state.route.

Config:
  prompt:   str   — system prompt para el clasificador
  routes:   list  — valores válidos (ej: ["noticias", "oficio", "auspiciante"])
  fallback: str   — route por defecto si el LLM no responde algo válido
  model:    str   — modelo Groq (default: llama-3.3-70b-versatile)
"""
import logging
import os
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class RouterNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        prompt   = self.config.get("prompt", "")
        routes   = self.config.get("routes", [])
        fallback = self.config.get("fallback", routes[0] if routes else "")
        model    = self.config.get("model", "llama-3.3-70b-versatile")

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or not prompt:
            logger.warning("[RouterNode] Sin GROQ_API_KEY o prompt — usando fallback '%s'", fallback)
            state.route = fallback
            return state

        try:
            from langchain_groq import ChatGroq
            llm = ChatGroq(model=model, api_key=api_key, max_tokens=10, temperature=0)
            result = await llm.ainvoke([
                {"role": "system", "content": prompt},
                {"role": "user",   "content": state.message},
            ])
            route = result.content.strip().lower()
            if routes and route not in routes:
                logger.info("[RouterNode] respuesta '%s' no válida — usando fallback '%s'", route, fallback)
                route = fallback
            logger.info("[RouterNode] route → '%s' | msg: %.60s", route, state.message)
            state.route = route
        except Exception as e:
            logger.error("[RouterNode] Error: %s — fallback '%s'", e, fallback)
            state.route = fallback

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "prompt":   {"type": "string", "label": "Prompt del clasificador",          "default": ""},
            "routes":   {"type": "list",   "label": "Rutas válidas (ej: a,b,c)",        "default": []},
            "fallback": {"type": "string", "label": "Ruta por defecto si LLM falla",    "default": ""},
            "model":    {"type": "string", "label": "Modelo",                           "default": "llama-3.3-70b-versatile"},
        }
