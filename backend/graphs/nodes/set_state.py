"""
SetStateNode — escribe un valor fijo en un campo del FlowState.

Útil para marcar datos antes de save_contact:
  set_state(field=contact_notes, value=herrería) → save_contact
"""
from .base import BaseNode
from .state import FlowState


class SetStateNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        field = self.config.get("field", "").strip()
        value = self.config.get("value", "")
        if field:
            if hasattr(state, field):
                setattr(state, field, value)
            else:
                state.vars[field] = value
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
