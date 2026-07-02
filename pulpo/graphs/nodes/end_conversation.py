"""
EndConversationNode — cierra explícitamente la conversación actual.

Marca todos los runs en waiting_gate de este (bot_id, contact_phone) como
'completed', liberando al dispatcher para que el próximo mensaje arranque un
flow nuevo en vez de retomar uno pausado.

Config opcional:
  farewell_message: str — mensaje de despedida enviado al usuario antes de cerrar.
                          Soporta {{placeholders}}. Útil cuando no hay nodo LLM previo.
                          Si está vacío, no se envía nada.
"""
import logging
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


class EndConversationNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        bot_id  = state.bot_id or ""
        contact = state.contact_phone or ""
        if not bot_id or not contact:
            logger.warning("[end_conv] sin bot_id o contact_phone — skip")
            return state

        farewell = interpolate(self.config.get("farewell_message", ""), state).strip()
        if farewell:
            state.data["reply"] = farewell

        try:
            from pulpo.core import db as _db
            closed = await _db.close_waiting_conversations(bot_id, contact)
            logger.info("[end_conv] bot=%s contact=%s cerró %d run(s)", bot_id, contact, closed)
        except Exception:
            logger.warning("[end_conv] error cerrando conversaciones (non-fatal)", exc_info=True)
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "farewell_message": {
                "type":    "textarea",
                "label":   "Mensaje de despedida (opcional)",
                "default": "",
                "rows":    3,
                "hint":    "Se envía al usuario al cerrar la conversación. Vacío = sin mensaje. Soporta {{placeholders}}.",
            },
        }
