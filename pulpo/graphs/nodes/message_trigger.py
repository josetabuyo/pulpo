"""
MessageTriggerNode — trigger genérico: aplica a cualquier canal.

Retrocompatibilidad con flows creados antes de los triggers por canal
(telegram_trigger, whatsapp_trigger). Para flows nuevos conviene usar
el trigger específico del canal.
"""
from .base_trigger import BaseTriggerNode


class MessageTriggerNode(BaseTriggerNode):
    channel = None
    connection_label = "Conexión"
