"""
Registro central de tipos de nodo para flows de agentes.

Un NodeType define todo lo necesario para representar un nodo en el editor:
  - id          → clave que viaja en el JSON
  - label       → nombre visible en la UI
  - color       → color del nodo en el grafo
  - description → texto del tooltip

Esta es la ÚNICA fuente de verdad. Ni el endpoint ni el frontend hardcodean esto.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeType:
    id: str
    label: str
    color: str
    description: str


# Tipos internos (no aparecen en la paleta de usuario)
_INTERNAL_TYPES: dict[str, NodeType] = {
    "start": NodeType(id="start", label="Inicio", color="#166534", description="Nodo de inicio del flow."),
    "end":   NodeType(id="end",   label="Fin",    color="#991b1b", description="Nodo de fin del flow."),
    "generic": NodeType(id="generic", label="Nodo", color="#475569", description="Nodo de tipo desconocido."),
}

NODE_TYPES: dict[str, NodeType] = {
    "message_trigger": NodeType(
        id="message_trigger",
        label="Trigger de mensaje",
        color="#166534",
        description="Punto de entrada genérico (cualquier canal). Usar whatsapp_trigger o telegram_trigger para flows nuevos.",
    ),
    "whatsapp_trigger": NodeType(
        id="whatsapp_trigger",
        label="WhatsApp Trigger",
        color="#16a34a",
        description="Punto de entrada para mensajes de WhatsApp. Solo activa el flow si el mensaje viene por WA.",
    ),
    "telegram_trigger": NodeType(
        id="telegram_trigger",
        label="Telegram Trigger",
        color="#0369a1",
        description="Punto de entrada para mensajes de Telegram. Solo activa el flow si el mensaje viene por TG.",
    ),
    "message_join": NodeType(
        id="message_join",
        label="+",
        color="#475569",
        description="Nodo de convergencia (fan-in). Úsalo cuando un flow tiene múltiples triggers. No modifica el estado.",
    ),
    "router": NodeType(
        id="router",
        label="Router",
        color="#854d0e",
        description="Clasifica el mensaje con LLM y decide qué rama ejecutar.",
    ),
    "llm": NodeType(
        id="llm",
        label="Respuesta LLM",
        color="#6b21a8",
        description="Genera una respuesta usando un modelo de lenguaje (Groq).",
    ),
    "send_message": NodeType(
        id="send_message",
        label="Enviar mensaje",
        color="#15803d",
        description="Envía un mensaje al usuario o a un contacto externo vía WA/TG.",
    ),
    "vector_search": NodeType(
        id="vector_search",
        label="Búsqueda vectorial",
        color="#0e7490",
        description="Busca en una colección (oficios, auspiciantes, etc.) y popula state.vars.",
    ),
    "fetch": NodeType(
        id="fetch",
        label="Fetch externo",
        color="#1e40af",
        description="Obtiene datos externos: posts de Facebook, imagen de post, o HTTP genérico.",
    ),
    "summarize": NodeType(
        id="summarize",
        label="Sumarizador",
        color="#14532d",
        description="Acumula mensajes en un archivo .md por contacto. Sin reply.",
    ),
    "set_state": NodeType(
        id="set_state",
        label="Establecer estado",
        color="#0891b2",
        description="Escribe un valor fijo en un campo del estado del flow.",
    ),
    "save_contact": NodeType(
        id="save_contact",
        label="Guardar contacto",
        color="#059669",
        description="Persiste el contacto en la base de datos usando datos del estado.",
    ),
    "transcribe_audio": NodeType(
        id="transcribe_audio",
        label="Transcribir audio",
        color="#7c3aed",
        description="Transcribe un mensaje de audio a texto usando Whisper. Colocar antes de summarize.",
    ),
    "save_attachment": NodeType(
        id="save_attachment",
        label="Guardar adjunto",
        color="#b45309",
        description="Mueve el adjunto a almacenamiento permanente (data/summaries/). Colocar entre transcribe_audio y summarize.",
    ),
    "check_contact": NodeType(
        id="check_contact",
        label="¿Contacto conocido?",
        color="#0e7490",
        description="Consulta la DB y setea la ruta: 'conocido' o 'desconocido'. Sin LLM — decisión pura.",
    ),
    "fetch_sheet": NodeType(
        id="fetch_sheet",
        label="Leer planilla",
        color="#16a34a",
        description="Lee una Google Sheet pública y vuelca el contenido completo en state.context.",
    ),
    "gsheet": NodeType(
        id="gsheet",
        label="Google Sheet",
        color="#16a34a",
        description="Busca una fila exacta en una Google Sheet, o agrega una fila nueva.",
    ),
    "search_sheet": NodeType(
        id="search_sheet",
        label="Buscar en planilla",
        color="#0e7490",
        description="Busca en una Google Sheet el ítem que coincide con el mensaje. Usa LLM para identificar el valor.",
    ),
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
    ("router",    "router"),
    ("summariz",  "summarize"),
    ("trigger",   "message_trigger"),
    ("llm",       "llm"),
    ("fetch",     "fetch"),
    ("vector",    "vector_search"),
    ("send",      "send_message"),
    ("set_state", "set_state"),
    ("save_contact", "save_contact"),
    ("transcribe", "transcribe_audio"),
    ("save_attachment", "save_attachment"),
    ("check_contact", "check_contact"),
    ("whatsapp_trigger", "whatsapp_trigger"),
    ("telegram_trigger", "telegram_trigger"),
    ("message_join", "message_join"),
    ("fetch_sheet",   "fetch_sheet"),
    ("search_sheet",  "search_sheet"),
    ("gsheet",        "gsheet"),
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
