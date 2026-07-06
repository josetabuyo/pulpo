"""
SetStateNode — escribe un valor en un campo del FlowState.

Soporta templates en `value`: {{message}}, {{contact_name}}, y cualquier
clave de state.data con {{clave}}. Útil para capturar la respuesta del
usuario después de un wait_user:
  set_state(field=direccion, value={{message}})
"""
from .base import BaseNode, interpolate
from .state import FlowState

# Derivado del dataclass — incluye todos los campos fijos excepto "data"
_META_FIELDS = frozenset(FlowState.__dataclass_fields__) - {"data"}


class SetStateNode(BaseNode):
    label = "Establecer estado"
    color = "#0891b2"
    description = "Escribe un valor fijo en un campo del estado del flow."

    async def run(self, state: FlowState) -> FlowState:
        field = self.config.get("field", "").strip()
        mode  = self.config.get("mode", "set")
        if not field:
            return state
        if mode == "increment":
            current = int(state.data.get(field, 0) or 0)
            value = str(current + 1)
        else:
            value = interpolate(self.config.get("value", ""), state)
        if field in _META_FIELDS:
            setattr(state, field, value)
        else:
            state.data[field] = value
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "field": {
                "type": "string",
                "label": "Campo del estado",
                "hint": "Ej: contact_notes",
                "required": True,
            },
            "value": {
                "type": "string",
                "label": "Valor a escribir",
                "required": True,
            },
        }
