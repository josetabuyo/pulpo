"""
ReplyNode — devuelve un mensaje de texto fijo.

Config:
  message: str   — texto a enviar
"""
from .base import BaseNode
from .state import FlowState


class ReplyNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        if state.from_delta_sync:
            return state
        state.reply = self.config.get("message", "")
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "message": {
                "type": "string",
                "label": "Mensaje a enviar",
                "default": "",
                "required": True,
            }
        }
