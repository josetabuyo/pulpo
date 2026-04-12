"""
TelegramTriggerNode — trigger específico para mensajes de Telegram.

Igual que WhatsappTriggerNode pero solo activa flows cuando state.canal == "telegram".
"""
from .base import BaseNode
from .state import FlowState


class TelegramTriggerNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "connection_id": {
                "type": "connection_select",
                "label": "Conexión Telegram",
                "default": "",
                "required": True,
            },
            "contact_filter": {
                "type": "contact_filter",
                "label": "Filtro de contactos",
                "default": {
                    "include_all_known": False,
                    "include_unknown": False,
                    "included": [],
                    "excluded": [],
                },
            },
            "message_pattern": {
                "type": "string",
                "label": "Patrón regex (opcional)",
                "default": "",
                "hint": "Deja vacío para cualquier mensaje.",
            },
            "cooldown_hours": {
                "type": "number",
                "label": "Cooldown entre respuestas (horas)",
                "default": 4,
                "hint": "Tiempo mínimo entre respuestas al mismo contacto. 0 = sin límite.",
            },
        }
