"""
EndConversationNode — cierra explícitamente la conversación actual.

Marca todos los runs en waiting_gate de este (bot_id, contact_phone) como
'completed', liberando al dispatcher para que el próximo mensaje arranque un
flow nuevo en vez de retomar uno pausado.

Responsabilidad única: cerrar. No envía ningún mensaje — para despedirse y
cerrar en un solo paso, usar el NodoFlow "reply_and_close" (send_message +
end_conversation compuestos, con `message` como único parámetro).
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class EndConversationNode(BaseNode):
    label = "Cerrar conversación"
    color = "#be123c"
    description = "Cierra explícitamente la conversación actual. El próximo mensaje del contacto abrirá un flow nuevo."

    async def run(self, state: FlowState) -> FlowState:
        bot_id  = state.bot_id or ""
        contact = state.contact_phone or ""
        if not bot_id or not contact:
            logger.warning("[end_conv] sin bot_id o contact_phone — skip")
            return state

        try:
            from pulpo.core import db as _db
            closed = await _db.close_waiting_conversations(bot_id, contact)
            await _db.close_open_conversation(bot_id, contact)
            # Señal para execute_flow(): no re-crear la fila que este nodo
            # acaba de borrar — el guardado de fin de run es incondicional
            # si state.data["conversation"] sigue poblado (que sigue estándolo,
            # solo lo vaciamos de open_conversations, no de la memoria del run).
            state.data["_conversation_closed"] = True
            logger.info("[end_conv] bot=%s contact=%s cerró %d run(s)", bot_id, contact, closed)
        except Exception:
            logger.warning("[end_conv] error cerrando conversaciones (non-fatal)", exc_info=True)
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {}
