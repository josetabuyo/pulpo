"""
NodoFlowNode — invoca otro flow como sub-flow.

Este nodo nunca se ejecuta directo: el compilador lo detecta en tiempo de
compilación y lo expande inline (sustituyéndolo por los nodos del flow
referenciado en `flow_id`). Si `run()` llega a ejecutarse, significa que esa
expansión no ocurrió — bug del compilador.

Config: solo `flow_id`, `output` y `routes` son reservadas — cualquier otra
clave se pasa tal cual como parámetro al sub-flow (sin anidar en un "params"
separado; las claves esperadas las declara el sub-flow en su propio
`definition.inputs`). `output`, si está seteado, también se reenvía como
parámetro `output` — el sub-flow lo usa vía `{{output}}` (ej. en el campo
`output` de un LLMNode interno) para saber en qué clave del estado del padre
escribir su resultado, sin ningún paso de copia posterior.
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
            "output": {
                "type": "string",
                "label": "Output (opcional)",
                "default": "",
                "hint": "Clave de state.data donde el sub-flow debería escribir su resultado. "
                        "Se reenvía al sub-flow como parámetro {{output}} — solo tiene efecto "
                        "si el sub-flow lo usa internamente (ej. en el campo 'output' de un "
                        "nodo LLM). Dejalo vacío si el sub-flow ya usa una clave fija.",
            },
            "routes": {
                "type": "list",
                "label": "Rutas de salida",
                "default": [],
                "hint": "Salidas nombradas del sub-flow elegido — la UI las auto-completa "
                        "al elegir 'Flow a invocar' (compute_exit_routes); documentan qué "
                        "labels usar en los edges salientes de este nodo.",
            },
        }
