"""
ApiTriggerNode — trigger via HTTP API.

Se activa cuando el endpoint POST /api/flows/{flow_id}/trigger recibe una
llamada. No requiere conexión, filtro de contactos, ni cooldown.
"""
from .base_trigger import BaseTriggerNode


class ApiTriggerNode(BaseTriggerNode):
    channel = "api"
    requires_connection = False

    @classmethod
    def config_schema(cls) -> dict:
        return {}
