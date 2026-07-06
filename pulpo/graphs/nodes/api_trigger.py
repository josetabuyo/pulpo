"""
ApiTriggerNode — trigger via HTTP API.

Se activa cuando el endpoint POST /api/flows/{flow_id}/trigger recibe una
llamada. No requiere conexión, filtro de contactos, ni cooldown.
"""
from .base_trigger import BaseTriggerNode


class ApiTriggerNode(BaseTriggerNode):
    label = "API Trigger"
    color = "#7c3aed"
    description = "Punto de entrada via HTTP. Activa el flow con un POST a /api/flows/{flow_id}/trigger."

    channel = "api"
    requires_connection = False

    @classmethod
    def config_schema(cls) -> dict:
        return {}
