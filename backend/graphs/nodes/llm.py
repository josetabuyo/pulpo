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
                # Guardar fb_posts image info si viene en el JSON
                if "needs_image" in data and data.get("needs_image") and state.fb_posts:
                    idx = int(data.get("source_post_index", -1))
                    state.route = state.route or "imagen"  # señal para edge condicional
                    if 0 <= idx < len(state.fb_posts):
                        state.image_url = state.fb_posts[idx].get("image_url", "")
                    if not state.image_url:
                        for post in state.fb_posts:
                            if post.get("image_url"):
                                state.image_url = post["image_url"]
                                break
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
            "prompt":         {"type": "string", "label": "System prompt",        "default": ""},
            "model":          {"type": "string", "label": "Modelo",               "default": "llama-3.3-70b-versatile"},
            "temperature":    {"type": "float",  "label": "Temperatura",          "default": 0.3},
            "output":         {"type": "select", "label": "Destino de la salida", "default": "reply",
                               "options": ["reply", "context", "query"]},
            "json_output":    {"type": "bool",   "label": "Respuesta JSON",       "default": False},
            "json_reply_key": {"type": "string", "label": "Clave JSON del reply", "default": "reply"},
        }
