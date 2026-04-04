"""
MessageTriggerNode — trigger específico para mensajes de texto.

Config:
  connection_id: str   — ID de la conexión (bot_id) que debe coincidir
  contact_phone: str   — número de teléfono del contacto (opcional, "" = wildcard)
  message_pattern: str — regex opcional para filtrar por contenido del mensaje

Este nodo no modifica el estado — solo sirve como guard que el engine verifica
antes de ejecutar el flow. Es el primer nodo trigger específico del nuevo
sistema data-driven.
"""
from .base import BaseNode
from .state import FlowState


class MessageTriggerNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        """
        MessageTriggerNode no modifica el estado.
        Su propósito es ser un guard que el engine verifica antes de ejecutar el flow.
        """
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "connection_id": {
                "type": "string",
                "label": "ID de conexión (bot_id)",
                "default": "",
                "required": True,
            },
            "contact_phone": {
                "type": "string",
                "label": "Teléfono del contacto (dejar vacío para todos)",
                "default": "",
                "required": False,
            },
            "message_pattern": {
                "type": "string",
                "label": "Patrón regex (opcional)",
                "default": "",
                "required": False,
                "description": "Filtrar por contenido del mensaje. Ej: .*urgente.*"
            }
        }