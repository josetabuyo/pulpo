"""
ReplyNode — escribe en state.reply el texto que se enviará al usuario.

Config:
  message: str — texto con placeholders opcionales: {{context}}, {{contact_name}}, etc.

Ejemplos:
  "Hola {{contact_name}}, te respondemos pronto."
  "{{context}}"               ← reenvía lo que dejó el nodo anterior en context
  "Texto fijo sin variables"
"""
from .base import BaseNode, interpolate
from .state import FlowState


class ReplyNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        if state.from_delta_sync:
            return state

        state.reply = interpolate(self.config.get("message", ""), state)
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "message": {
                "type": "string",
                "label": "Mensaje (soporta {{placeholders}})",
                "default": "",
                "required": True,
            },
        }
