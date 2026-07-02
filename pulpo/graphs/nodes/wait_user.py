"""
WaitUserNode — pausa el flow y espera la próxima respuesta del contacto.

Diferencia vs GateNode (AND-join): este nodo siempre bloquea la primera vez.
El compiler detecta el bloqueo, persiste el estado (slots) y el nodo de reanudación
en DB, y marca el run como 'waiting_gate'. Cuando el mismo contacto envía un
nuevo mensaje, el dispatcher en run_flows retoma la ejecución desde el nodo
siguiente a este, con el estado previo restaurado y el nuevo mensaje en state.message.

No tiene config: basta con conectarlo en el flow. El timeout/expiración de
conversaciones colgadas se maneja externamente (no en este nodo).
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class WaitUserNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        node_id = self.config.get("_node_id", "wait_user")
        logger.info("[wait_user] node=%s contact=%s — pausando flow, esperando respuesta",
                    node_id, state.contact_phone)
        state.data["_gate_blocked"] = True
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {}
