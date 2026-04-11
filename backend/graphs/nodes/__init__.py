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
from .set_state import SetStateNode
from .save_contact import SaveContactNode

NODE_REGISTRY: dict[str, type] = {
    "message_trigger": MessageTriggerNode,
    "router":          RouterNode,
    "llm":             LLMNode,
    "send_message":    SendMessageNode,
    "fetch":           FetchNode,
    "vector_search":   VectorSearchNode,
    "summarize":       SummarizeNode,
    "set_state":       SetStateNode,
    "save_contact":    SaveContactNode,
}

__all__ = [
    "NODE_REGISTRY",
    "MessageTriggerNode", "RouterNode", "LLMNode", "SendMessageNode",
    "FetchNode", "VectorSearchNode", "SummarizeNode",
    "SetStateNode", "SaveContactNode",
]
