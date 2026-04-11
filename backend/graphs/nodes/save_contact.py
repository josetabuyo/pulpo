"""
SaveContactNode — persiste en DB lo que ya está en el FlowState.

Tonto por diseño: no decide cuándo guardar. Solo lee campos del state
y llama a db.create_contact / db.update_contact.

Flujo típico:
  set_state(field=contact_notes, value=herrería) → save_contact
"""
from .base import BaseNode
from .state import FlowState


class SaveContactNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        empresa_id = state.empresa_id or ""
        name_field  = self.config.get("name_field",  "contact_name")
        phone_field = self.config.get("phone_field", "contact_phone")
        notes_field = self.config.get("notes_field", "contact_notes")
        update      = self.config.get("update_if_exists", True)

        def _get(field):
            v = getattr(state, field, None)
            if v:
                return v
            return state.vars.get(field)

        name  = _get(name_field)  or state.contact_phone
        phone = _get(phone_field) or state.contact_phone
        notes = _get(notes_field)

        if not name or not empresa_id:
            return state

        import db
        existing = await db.find_contact_by_channel("whatsapp", phone) if phone else None
        if existing and update:
            await db.update_contact(existing["id"], name, notes=notes)
        elif not existing:
            contact_id = await db.create_contact(empresa_id, name, notes=notes)
            if phone:
                try:
                    await db.add_channel(contact_id, "whatsapp", phone)
                except Exception:
                    pass
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "name_field": {
                "type": "string",
                "label": "Campo → nombre",
                "default": "contact_name",
            },
            "phone_field": {
                "type": "string",
                "label": "Campo → teléfono",
                "default": "contact_phone",
            },
            "notes_field": {
                "type": "string",
                "label": "Campo → notas",
                "default": "contact_notes",
                "hint": "Ej: trade, category",
            },
            "update_if_exists": {
                "type": "bool",
                "label": "Actualizar si ya existe",
                "default": True,
            },
        }
