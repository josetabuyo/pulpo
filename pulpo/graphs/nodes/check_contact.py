"""
CheckContactNode — decide si el contacto está registrado en la DB.

Consulta contact_channels para el bot_id y contact_phone actuales.
Setea state.route a 'conocido' o 'desconocido' (configurable).
También escribe state.vars["es_conocido"] = "true"/"false" para usar en prompts.

No usa LLM — es una decisión pura basada en la DB.
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class CheckContactNode(BaseNode):
    label = "¿Contacto conocido?"
    color = "#0e7490"
    description = "Consulta la DB y setea la ruta: 'conocido' o 'desconocido'. Sin LLM — decisión pura."

    async def run(self, state: FlowState) -> FlowState:
        route_known   = self.config.get("route_known",   "conocido")
        route_unknown = self.config.get("route_unknown", "desconocido")

        from pulpo.core.db import AsyncSessionLocal, text as _text
        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                _text("""
                    SELECT cc.id FROM contact_channels cc
                    JOIN contacts c ON cc.contact_id = c.id
                    WHERE cc.value = :phone
                      AND c.bot_id = :bot_id
                    LIMIT 1
                """),
                {"phone": state.contact_phone, "bot_id": state.bot_id},
            )).fetchone()

        is_known = row is not None
        state.data["es_conocido"] = "true" if is_known else "false"
        state.data["route"] = route_known if is_known else route_unknown

        logger.info(
            "[CheckContactNode] %s → %s (bot=%s)",
            state.contact_phone, state.data.get("route"), state.bot_id,
        )
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "route_known": {
                "type": "string",
                "label": "Ruta si es conocido",
                "default": "conocido",
            },
            "route_unknown": {
                "type": "string",
                "label": "Ruta si es desconocido",
                "default": "desconocido",
            },
        }
