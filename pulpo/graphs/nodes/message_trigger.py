"""
MessageTriggerNode — trigger genérico: aplica a cualquier canal.

Retrocompatibilidad con flows creados antes de los triggers por canal
(telegram_trigger, whatsapp_trigger). Para flows nuevos conviene usar
el trigger específico del canal.
"""
from .base_trigger import BaseMessageTriggerNode


class MessageTriggerNode(BaseMessageTriggerNode):
    label = "Trigger de mensaje"
    color = "#166534"
    description = "Punto de entrada genérico (cualquier canal). Usar telegram_trigger para flows nuevos."

    channel = None
    connection_label = "Conexión"
