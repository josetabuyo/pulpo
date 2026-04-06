"""
Registro de nodos ejecutables.

NODE_REGISTRY mapea type_id (string del JSON de definición)
→ clase de nodo que implementa BaseNode.

Para agregar un nodo nuevo:
  1. Crear su módulo en graphs/nodes/
  2. Importarlo aquí
  3. Agregarlo al registro
"""
from .message_trigger import MessageTriggerNode
from .reply import SendMessageNode
from .summarize import SummarizeNode
from .router import RouterNode
from .llm import LLMNode
from .fetch import FetchNode
from .vector_search import VectorSearchNode

NODE_REGISTRY: dict[str, type] = {
    "message_trigger": MessageTriggerNode,
    "router":          RouterNode,
    "llm":             LLMNode,
    "send_message":    SendMessageNode,
    "fetch":           FetchNode,
    "vector_search":   VectorSearchNode,
    "summarize":       SummarizeNode,
}

__all__ = [
    "NODE_REGISTRY",
    "MessageTriggerNode", "RouterNode", "LLMNode", "SendMessageNode",
    "FetchNode", "VectorSearchNode", "SummarizeNode",
]
