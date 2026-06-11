"""
WhatsappTriggerNode — trigger específico de WhatsApp via Wavi.

Solo activa flows cuando state.canal == "wavi".
"""
from .base_trigger import BaseTriggerNode


class WhatsappTriggerNode(BaseTriggerNode):
    channel = "wavi"
    connection_label = "Conexión WhatsApp"
