"""
LLMRespondNode — responde usando un LLM (Groq / Llama) con contexto estático.

Config:
  prompt: str    — contexto del sistema
  model:  str    — modelo a usar (default: llama-3.3-70b-versatile)
"""
import logging
import os
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class LLMRespondNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        if state.from_delta_sync:
            return state

        context = self.config.get("prompt", "")
        model = self.config.get("model", _DEFAULT_MODEL)

        if not context:
            logger.warning("[LLMRespondNode] Sin prompt configurado para empresa '%s'", state.empresa_id)
            return state

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("[LLMRespondNode] GROQ_API_KEY no configurada")
            return state

        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=api_key)
            system = (
                f"Sos el asistente de {state.bot_name}. "
                "Respondé solo con la información del siguiente contexto. "
                "Si no encontrás la respuesta en el contexto, decí que no tenés esa información. "
                "Respondé en español, de forma breve y amigable.\n\n"
                f"Contexto:\n{context}"
            )
            response = await client.chat.completions.create(
                model=model,
                max_tokens=400,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": state.message},
                ],
            )
            state.reply = response.choices[0].message.content
        except Exception as e:
            logger.error("[LLMRespondNode] Error llamando a Groq: %s", e)

        return state
