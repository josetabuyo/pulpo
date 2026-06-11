"""
TelegramTriggerNode — trigger específico de Telegram.

Solo activa flows cuando state.canal == "telegram".
"""
from .base_trigger import BaseTriggerNode


class TelegramTriggerNode(BaseTriggerNode):
    channel = "telegram"
    connection_label = "Conexión Telegram"
