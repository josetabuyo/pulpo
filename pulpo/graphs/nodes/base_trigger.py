"""
BaseTriggerNode — base común de todos los triggers.

Un trigger es un guard: no muta el estado. La decisión de si el flow aplica
la toma graphs/trigger_match.py usando el config del trigger (connection_id,
contact_filter, message_pattern, cooldown_hours) y estos atributos de clase:

  channel          — canal requerido ("telegram", "wavi") o None = cualquiera
  connection_label — label del selector de conexión en la UI

Para agregar un trigger nuevo alcanza con subclasear y registrarlo en
NODE_REGISTRY: TRIGGER_TYPES se deriva automáticamente y el engine
no necesita cambios.
"""
from .base import BaseNode
from .state import FlowState


class BaseTriggerNode(BaseNode):
    channel: str | None = None
    connection_label: str = "Conexión"

    async def run(self, state: FlowState) -> FlowState:
        # Los triggers son guards — el filtrado ya ocurrió en trigger_match.
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "connection_id": {
                "type": "connection_select",
                "label": cls.connection_label,
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
                "hint": "Deja vacío para cualquier mensaje. Ej: .*urgente.*",
            },
            "cooldown_hours": {
                "type": "number",
                "label": "Cooldown entre respuestas (horas)",
                "default": 4,
                "hint": "Tiempo mínimo entre respuestas al mismo contacto. 0 = sin límite.",
            },
        }
