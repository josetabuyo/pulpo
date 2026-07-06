"""
TelegramTriggerNode — trigger específico de Telegram.

Solo activa flows cuando state.canal == "telegram".
"""
from .base_trigger import BaseTriggerNode


class TelegramTriggerNode(BaseTriggerNode):
    label = "Telegram Trigger"
    color = "#0369a1"
    description = "Punto de entrada para mensajes de Telegram. Solo activa el flow si el mensaje viene por TG."

    channel = "telegram"
    connection_label = "Conexión Telegram"
