"""
GateNode — nodo AND de convergencia bloqueante.

Espera que N caminos distintos lleguen al nodo antes de continuar el flow.
Cada vez que un trigger/camino alcanza el gate, acumula el mensaje entrante.
Cuando se completan las N entradas, continúa con:
  state.data["gate_messages"] = [msg1, msg2, ...]

A diferencia de MessageJoinNode (pass-through), el gate bloquea el BFS
hasta que todos los caminos configurados hayan llegado.

Señal al engine: cuando bloquea, escribe state.data["_gate_blocked"] = True.
El BFS no encola vecinos hasta que el contador se complete.
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)

# Store en memoria: (node_id, contact_phone) -> lista de mensajes acumulados.
# Persiste mientras el proceso esté corriendo — se limpia al completar el gate.
_GATE_STORE: dict[tuple[str, str], list[str]] = {}


class GateNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        node_id: str = self.config.get("_node_id", "gate")
        wait_for: int = int(self.config.get("_in_degree", 2))
        contact: str = state.contact_phone or ""

        key = (node_id, contact)
        _GATE_STORE.setdefault(key, []).append(state.message or "")
        count = len(_GATE_STORE[key])

        logger.debug("[gate] node=%s contact=%s %d/%d", node_id, contact, count, wait_for)

        if count < wait_for:
            state.data["_gate_blocked"] = True
            return state

        state.data["gate_messages"] = _GATE_STORE.pop(key)
        logger.info("[gate] node=%s contact=%s abierto con %d mensajes", node_id, contact, count)
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {}
