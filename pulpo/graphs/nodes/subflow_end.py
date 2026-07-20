"""
SubflowEndNode — ancla de salida de un sub-flow (flow_kind == "node_flow").

Como SubflowStartNode, es un passthrough puro que SÍ se ejecuta (no modifica
`state.data`). Marca, de forma explícita en el canvas, un punto de salida del
sub-flow. Un sub-flow puede tener VARIOS `subflow_end` — uno por cada ruta de
salida que expone al flow padre.

El compilador (`expand_node_flows`) usa `config.route` de cada `subflow_end`
como el label de salida para reconectar los edges externos del nodo `nodo_flow`
que invoca al sub-flow (ver expand_node_flows y compute_exit_routes). Un `route`
vacío/None representa una salida sin nombre (el caso de una sola salida).

Config:
  route: str — nombre de la ruta de salida (puede quedar vacío para una única
               salida sin nombre).
"""
from .base import BaseNode
from .state import FlowState


class SubflowEndNode(BaseNode):
    label = "Fin de sub-flow"
    color = "#0d9488"
    description = "Marca un punto de salida de un sub-flow (NodoFlow). Passthrough — no modifica el estado."

    async def run(self, state: FlowState) -> FlowState:
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "route": {
                "type": "string",
                "label": "Ruta de salida",
                "default": "",
                "hint": "Nombre de la salida (label del edge en el flow padre). Vacío = única salida sin nombre.",
            },
        }
