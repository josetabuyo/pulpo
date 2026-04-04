"""
Registro de nodos ejecutables.

NODE_REGISTRY mapea type_id (string del JSON de definición)
→ clase de nodo que implementa BaseNode.

Para agregar un nodo nuevo:
  1. Crear su módulo en graphs/nodes/
  2. Importarlo aquí
  3. Agregarlo al registro
"""
from .reply import ReplyNode
from .llm_respond import LLMRespondNode
from .summarize import SummarizeNode
from .luganense_flow import LuganenseFlowNode
from .message_trigger import MessageTriggerNode

NODE_REGISTRY: dict[str, type] = {
    # Triggers data-driven
    "message_trigger": MessageTriggerNode,

    # Nodos de acción
    "reply":          ReplyNode,
    "llm_respond":    LLMRespondNode,
    "summarize":      SummarizeNode,
    "luganense_flow": LuganenseFlowNode,
}

__all__ = [
    "NODE_REGISTRY",
    "MessageTriggerNode",
    "ReplyNode",
    "LLMRespondNode",
    "SummarizeNode",
    "LuganenseFlowNode",
]
