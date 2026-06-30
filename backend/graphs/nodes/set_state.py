"""
SetStateNode — escribe un valor fijo en un campo del FlowState.

Útil para marcar datos antes de save_contact:
  set_state(field=contact_notes, value=herrería) → save_contact
"""
from .base import BaseNode
from .state import FlowState

# Derivado del dataclass — incluye todos los campos fijos excepto "data"
_META_FIELDS = frozenset(FlowState.__dataclass_fields__) - {"data"}


class SetStateNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        field = self.config.get("field", "").strip()
        value = self.config.get("value", "")
        if field:
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
