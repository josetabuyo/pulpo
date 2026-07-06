"""
WhatsappTriggerNode — trigger específico de WhatsApp via Wavi.

Solo activa flows cuando state.canal == "wavi".
"""
from .base_trigger import BaseTriggerNode


class WhatsappTriggerNode(BaseTriggerNode):
    label = "WhatsApp Trigger"
    color = "#15803d"
    description = "Punto de entrada para mensajes de WhatsApp (Wavi). Solo activa el flow si el mensaje viene por WA."

    channel = "wavi"
    connection_label = "Conexión WhatsApp"
