"""
WhatsappTriggerV2Node — trigger para mensajes de WhatsApp vía OpenWA.

Idéntico a WhatsappTriggerNode pero usa canal="whatsapp_v2".
El nodo es un no-op puro — la lógica de validación la hace el engine en compiler.py.
"""
from .base import BaseNode
from .state import FlowState


class WhatsappTriggerV2Node(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "connection_id": {
                "type": "connection_select",
                "label": "Conexión WhatsApp",
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
            "sync_interval_minutes": {
                "type": "number",
                "label": "Intervalo de sync del sumarizador (minutos)",
                "default": 4,
                "hint": "Cada cuántos minutos se sincroniza el sumarizador automáticamente. 0 = desactivado.",
            },
        }
