"""
Registro central de tipos de nodo para flows de agentes.

Un NodeType define todo lo necesario para representar un nodo en el editor:
  - id          → clave que viaja en el JSON
  - label       → nombre visible en la UI
  - color       → color del nodo en el grafo
  - description → texto del tooltip

La ÚNICA fuente de verdad es la propia clase de cada nodo (label/color/description
como class attributes, ver BaseNode en nodes/base.py) registrada en NODE_REGISTRY.
NODE_TYPES se deriva de ahí — agregar un nodo nuevo nunca requiere tocar este dict.
"""
from dataclasses import dataclass

from .nodes import NODE_REGISTRY


@dataclass(frozen=True)
class NodeType:
    id: str
    label: str
    color: str
    description: str


# Tipos internos (no aparecen en la paleta de usuario, no tienen clase en NODE_REGISTRY)
_INTERNAL_TYPES: dict[str, NodeType] = {
    "start": NodeType(id="start", label="Inicio", color="#166534", description="Nodo de inicio del flow."),
    "end":   NodeType(id="end",   label="Fin",    color="#991b1b", description="Nodo de fin del flow."),
    "generic": NodeType(id="generic", label="Nodo", color="#475569", description="Nodo de tipo desconocido."),
}

NODE_TYPES: dict[str, NodeType] = {
    type_id: NodeType(id=type_id, label=cls.label, color=cls.color, description=cls.description)
    for type_id, cls in NODE_REGISTRY.items()
}


def get(type_id: str) -> NodeType:
    """Retorna el NodeType correspondiente. Fallback a 'generic' si no existe."""
    return NODE_TYPES.get(type_id) or _INTERNAL_TYPES.get(type_id) or _INTERNAL_TYPES["generic"]


# Patrones para identificar el tipo a partir del ID del nodo (nombres semánticos en flows)
_CLASSIFY_PATTERNS: list[tuple[str, str]] = [
    ("__start__", "start"),
    ("__end__",   "end"),
]
_CLASSIFY_SUBSTRINGS: list[tuple[str, str]] = [
    ("condition", "condition"),
    ("router",    "router"),
    ("summariz",  "summarize"),
    ("whatsapp_trigger", "whatsapp_trigger"),
    ("telegram_trigger", "telegram_trigger"),
    ("api_trigger",      "api_trigger"),
    ("trigger",   "message_trigger"),
    ("llm",       "llm"),
    ("fetch_fb",  "fetch_fb"),
    ("fetch_http", "fetch_http"),
    ("vector",    "vector_search"),
    ("send",      "send_message"),
    ("set_state", "set_state"),
    ("save_contact", "save_contact"),
    ("transcribe", "transcribe_audio"),
    ("save_attachment", "save_attachment"),
    ("check_contact", "check_contact"),
    ("telegram_trigger", "telegram_trigger"),
    ("message_join", "message_join"),
    ("gate",          "gate"),
    ("wait_user",          "wait_user"),
    ("fetch_sheet",        "fetch_sheet"),
    ("search_sheet",       "search_sheet"),
    ("gsheet",             "gsheet"),
    ("detect_conversation", "detect_conversation"),
    ("end_conversation",    "end_conversation"),
    ("metric",              "metric"),
]


def classify(node_id: str) -> NodeType:
    """
    Infiere el tipo de nodo a partir de su ID semántico.

    Útil para flows legacy o nodos cuyo type no está en el JSON.
    Retorna 'generic' si no se puede inferir.
    """
    for exact, type_id in _CLASSIFY_PATTERNS:
        if node_id == exact:
            return get(type_id)
    node_lower = node_id.lower()
    for substring, type_id in _CLASSIFY_SUBSTRINGS:
        if substring in node_lower:
            return get(type_id)
    return _INTERNAL_TYPES["generic"]
