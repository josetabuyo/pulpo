"""
NodoFlowNode — invoca otro flow como sub-flow.

Este nodo nunca se ejecuta directo: el compilador lo detecta en tiempo de
compilación y lo expande inline (sustituyéndolo por los nodos del flow
referenciado en `flow_id`), pasándole `params` y guardando el resultado en
`output` dentro del estado del flow padre. Si `run()` llega a ejecutarse,
significa que esa expansión no ocurrió — bug del compilador.
"""
from .base import BaseNode
from .state import FlowState


class NodoFlowNode(BaseNode):
    label = "Sub-flow"
    color = "#db2777"
    description = "Invoca otro flow como sub-flow (se expande en tiempo de compilación)."

    async def run(self, state: FlowState) -> FlowState:
        raise RuntimeError("NodoFlowNode no debe ejecutarse directo — bug de expansión en el compilador")

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "flow_id": {
                "type": "select",
                "label": "Flow a invocar",
                "default": "",
                "options": [],
                "required": True,
            },
            "params": {
                "type": "dict",
                "label": "Parámetros",
                "default": {},
            },
            "output": {
                "type": "string",
                "label": "Clave de destino en el estado del padre",
                "default": "",
            },
        }
