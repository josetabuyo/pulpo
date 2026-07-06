"""
MessageJoinNode — nodo de convergencia visual (no-op).

Cuando un flow tiene múltiples triggers (whatsapp_trigger + telegram_trigger),
ambos apuntan a este nodo. Visualmente muestra que los caminos se unen.
No modifica el estado — el BFS ya maneja la convergencia solo (visited set).

Equivalente al nodo Merge (Pass-Through) de n8n / fan-in de LangGraph.
"""
from .base import BaseNode
from .state import FlowState


class MessageJoinNode(BaseNode):
    label = "+"
    color = "#475569"
    description = "Nodo de convergencia (fan-in). Úsalo cuando un flow tiene múltiples triggers. No modifica el estado."

    async def run(self, state: FlowState) -> FlowState:
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {}
