"""
Registro de nodos ejecutables.

NODE_REGISTRY mapea type_id (string del JSON de definición)
→ clase de nodo que implementa BaseNode.

Para agregar un nodo nuevo:
  1. Crear su módulo en graphs/nodes/
  2. Importarlo aquí
  3. Agregarlo al registro

TRIGGER_TYPES se deriva del registro: todo nodo que subclasee BaseTriggerNode
es un trigger — no hace falta tocar el engine para agregar uno nuevo.

MESSAGE_TRIGGER_TYPES es el subconjunto que subclasea BaseMessageTriggerNode —
triggers de un canal de mensajería humana (WhatsApp, Telegram, y los que se
agreguen a futuro). Solo esos flows acumulan conversación (ver graphs/conversation.py):
un flow puede existir sin ser una conversación (ej. api_trigger).
"""
from .base_trigger import BaseTriggerNode, BaseMessageTriggerNode
from .message_trigger import MessageTriggerNode
from .reply import SendMessageNode
from .summarize import SummarizeNode
from .router import RouterNode
from .condition import ConditionNode
from .llm import LLMNode
from .fetch_http import FetchHttpNode
from .vector_search import VectorSearchNode
from .set_state import SetStateNode
from .save_contact import SaveContactNode
from .check_contact import CheckContactNode
from .transcribe_audio import TranscribeAudioNode
from .save_attachment import SaveAttachmentNode
from .telegram_trigger import TelegramTriggerNode
from .whatsapp_trigger import WhatsappTriggerNode
from .api_trigger import ApiTriggerNode
from .message_join import MessageJoinNode
from .gate import GateNode
from .wait_user import WaitUserNode
from .fetch_sheet import FetchSheetNode
from .gsheet import GSheetNode
from .search_sheet import SearchSheetNode
from .detect_conversation import DetectConversationNode
from .end_conversation import EndConversationNode
from .metric import MetricNode
from .nodo_flow import NodoFlowNode

NODE_REGISTRY: dict[str, type] = {
    "message_trigger":    MessageTriggerNode,
    "telegram_trigger":   TelegramTriggerNode,
    "whatsapp_trigger":   WhatsappTriggerNode,
    "api_trigger":        ApiTriggerNode,
    "message_join":      MessageJoinNode,
    "gate":             GateNode,
    "wait_user":        WaitUserNode,
    "router":           RouterNode,
    "condition":        ConditionNode,
    "llm":              LLMNode,
    "send_message":     SendMessageNode,
    "fetch_http":       FetchHttpNode,
    "vector_search":    VectorSearchNode,
    "summarize":        SummarizeNode,
    "set_state":        SetStateNode,
    "save_contact":     SaveContactNode,
    "check_contact":    CheckContactNode,
    "transcribe_audio": TranscribeAudioNode,
    "save_attachment":  SaveAttachmentNode,
    "fetch_sheet":          FetchSheetNode,
    "gsheet":               GSheetNode,
    "search_sheet":         SearchSheetNode,
    "detect_conversation":  DetectConversationNode,
    "end_conversation":     EndConversationNode,
    "metric":               MetricNode,
    "nodo_flow":            NodoFlowNode,
}

# Tipos de nodo que actúan como entrada de un flow.
TRIGGER_TYPES: frozenset[str] = frozenset(
    type_id for type_id, cls in NODE_REGISTRY.items()
    if issubclass(cls, BaseTriggerNode)
)

# Subconjunto de TRIGGER_TYPES que representa un canal de mensajería humana.
MESSAGE_TRIGGER_TYPES: frozenset[str] = frozenset(
    type_id for type_id, cls in NODE_REGISTRY.items()
    if issubclass(cls, BaseMessageTriggerNode)
)

__all__ = [
    "NODE_REGISTRY", "TRIGGER_TYPES", "MESSAGE_TRIGGER_TYPES",
    "BaseTriggerNode", "BaseMessageTriggerNode",
    "MessageTriggerNode", "RouterNode", "ConditionNode", "LLMNode", "SendMessageNode",
    "FetchHttpNode", "VectorSearchNode", "SummarizeNode",
    "SetStateNode", "SaveContactNode",
    "TranscribeAudioNode", "SaveAttachmentNode",
    "TelegramTriggerNode", "WhatsappTriggerNode", "ApiTriggerNode", "MessageJoinNode",
    "CheckContactNode",
    "FetchSheetNode", "GSheetNode",
    "GateNode",
    "WaitUserNode",
    "DetectConversationNode",
    "EndConversationNode",
    "MetricNode",
    "NodoFlowNode",
]
