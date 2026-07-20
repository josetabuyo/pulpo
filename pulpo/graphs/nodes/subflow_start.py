"""
SubflowStartNode — ancla de entrada de un sub-flow (flow_kind == "node_flow").

A diferencia de NodoFlowNode (que nunca corre — se expande en compilación), este
nodo SÍ se ejecuta: es un passthrough puro que no toca `state.data`. Su única
razón de ser es marcar, de forma explícita y visible en el canvas del editor,
cuál es el punto de entrada del sub-flow — así el compilador
(`expand_node_flows`) no necesita inferir la raíz por heurística de in-degree.

Un sub-flow debe tener EXACTAMENTE UN `subflow_start` (ver expand_node_flows).

Config:
  key: str — identificador de la entrada (default "start"). Reservado para el
             futuro (múltiples entradas nombradas); en v1 no se usa para
             seleccionar — cualquier sub-flow tiene una sola entrada.
"""
from .base import BaseNode
from .state import FlowState


class SubflowStartNode(BaseNode):
    label = "Inicio de sub-flow"
    color = "#059669"
    description = "Marca el punto de entrada de un sub-flow (NodoFlow). Passthrough — no modifica el estado."

    async def run(self, state: FlowState) -> FlowState:
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "key": {
                "type": "string",
                "label": "Clave de entrada",
                "default": "start",
                "hint": "Reservado para múltiples entradas a futuro. En v1 no se usa para seleccionar.",
            },
        }
