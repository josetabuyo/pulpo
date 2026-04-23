"""
LLMNode — llama a un LLM con prompt configurable.

Config:
  prompt:      str   — system prompt
  model:       str   — modelo Groq (default: llama-3.3-70b-versatile)
  temperature: float — temperatura (default: 0.3)
  output:      str   — dónde guardar la respuesta:
                        "reply"   → state.reply (responde al usuario)
                        "context" → state.context (para el siguiente nodo)
                        "query"   → state.query (para fetch/search)
  json_output: bool  — pedir respuesta JSON (para nodos que devuelven estructurado)
  json_reply_key: str — clave del JSON que contiene el reply (default: "reply")
  json_route_key: str — clave del JSON que contiene el route (opcional)
"""
import json
import logging
import os
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


class LLMNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        if state.from_delta_sync:
            return state

        prompt      = self.config.get("prompt", "")
        model       = self.config.get("model", "llama-3.3-70b-versatile")
        temperature = float(self.config.get("temperature", 0.3))
        output      = self.config.get("output", "reply")
        json_out    = bool(self.config.get("json_output", False))
        reply_key   = self.config.get("json_reply_key", "reply")
        route_key   = self.config.get("json_route_key", "")

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("[LLMNode] Sin GROQ_API_KEY")
            return state

        # Interpolar placeholders en el prompt y construir system.
        # Compat: si el prompt no menciona {{context}} pero hay contexto, se agrega al final.
        system = interpolate(prompt, state)
        if state.context and "{{context}}" not in prompt:
            system += f"\n\nContexto:\n{state.context}"

        try:
            from langchain_groq import ChatGroq
            kwargs: dict = {}
            if json_out:
                kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

            llm = ChatGroq(model=model, api_key=api_key, temperature=temperature, **kwargs)
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
            "prompt":         {"type": "textarea", "label": "System prompt",        "default": "", "rows": 8},
            "model":          {"type": "select",   "label": "Modelo",               "default": "llama-3.3-70b-versatile",
                               "options": [
                                   {"value": "llama-3.3-70b-versatile",  "label": "llama-3.3-70b-versatile (recomendado)"},
                                   {"value": "llama-3.1-70b-versatile",  "label": "llama-3.1-70b-versatile"},
                                   {"value": "llama-3.1-8b-instant",     "label": "llama-3.1-8b-instant (rápido)"},
                                   {"value": "llama3-70b-8192",          "label": "llama3-70b-8192"},
                                   {"value": "llama3-8b-8192",           "label": "llama3-8b-8192"},
                                   {"value": "mixtral-8x7b-32768",       "label": "mixtral-8x7b-32768"},
                                   {"value": "gemma2-9b-it",             "label": "gemma2-9b-it"},
                               ]},
            "temperature":    {"type": "float",    "label": "Temperatura",          "default": 0.3},
            "output":         {"type": "select",   "label": "Destino de la salida", "default": "reply",
                               "hint": "reply = responde al usuario · context = pasa al siguiente nodo · query = para búsqueda/fetch",
                               "options": [
                                   {"value": "reply",   "label": "reply — responde al usuario"},
                                   {"value": "context", "label": "context — pasa al siguiente nodo"},
                                   {"value": "query",   "label": "query — para búsqueda vectorial / fetch"},
                               ]},
            "json_output":    {"type": "bool",     "label": "Respuesta JSON",       "default": False},
            "json_reply_key": {"type": "string",   "label": "Clave JSON del reply", "default": "reply",
                               "hint": "Clave dentro del JSON que contiene el texto a responder",
                               "show_if": {"json_output": True}},
        }
