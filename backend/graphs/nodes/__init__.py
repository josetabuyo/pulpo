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
from .check_contact import CheckContactNode
from .transcribe_audio import TranscribeAudioNode
from .save_attachment import SaveAttachmentNode
from .whatsapp_trigger import WhatsappTriggerNode
from .telegram_trigger import TelegramTriggerNode
from .message_join import MessageJoinNode
from .fetch_sheet import FetchSheetNode
from .gsheet import GSheetNode
from .search_sheet import SearchSheetNode

NODE_REGISTRY: dict[str, type] = {
    "message_trigger":   MessageTriggerNode,
    "whatsapp_trigger":  WhatsappTriggerNode,
    "telegram_trigger":  TelegramTriggerNode,
    "message_join":      MessageJoinNode,
    "router":           RouterNode,
    "llm":              LLMNode,
    "send_message":     SendMessageNode,
    "fetch":            FetchNode,
    "vector_search":    VectorSearchNode,
    "summarize":        SummarizeNode,
    "set_state":        SetStateNode,
    "save_contact":     SaveContactNode,
    "check_contact":    CheckContactNode,
    "transcribe_audio": TranscribeAudioNode,
    "save_attachment":  SaveAttachmentNode,
    "fetch_sheet":      FetchSheetNode,
    "gsheet":           GSheetNode,
    "search_sheet":     SearchSheetNode,
}

__all__ = [
    "NODE_REGISTRY",
    "MessageTriggerNode", "RouterNode", "LLMNode", "SendMessageNode",
    "FetchNode", "VectorSearchNode", "SummarizeNode",
    "SetStateNode", "SaveContactNode",
    "TranscribeAudioNode", "SaveAttachmentNode",
    "WhatsappTriggerNode", "TelegramTriggerNode", "MessageJoinNode",
    "CheckContactNode",
    "FetchSheetNode", "GSheetNode",
]
