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
from .search import SearchNode
from .notify import NotifyNode

NODE_REGISTRY: dict[str, type] = {
    # Triggers
    "message_trigger": MessageTriggerNode,

    # Nodos genéricos
    "router":       RouterNode,
    "llm":          LLMNode,
    "send_message": SendMessageNode,
    "fetch":        FetchNode,
    "search":       SearchNode,
    "notify":       NotifyNode,
    "summarize":    SummarizeNode,

    # Alias de compatibilidad
    "llm_respond": LLMNode,
}

__all__ = [
    "NODE_REGISTRY",
    "MessageTriggerNode",
    "RouterNode",
    "LLMNode",
    "SendMessageNode",
    "FetchNode",
    "SearchNode",
    "NotifyNode",
    "SummarizeNode",
]
