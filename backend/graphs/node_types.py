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


NODE_TYPES: dict[str, NodeType] = {
    "message_trigger": NodeType(
        id="message_trigger",
        label="Trigger de mensaje",
        color="#166534",
        description="Punto de entrada del flow. Filtra por conexión, contacto y patrón de mensaje.",
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
}


def get(type_id: str) -> NodeType | None:
    """Retorna el NodeType correspondiente, o None si no existe."""
    return NODE_TYPES.get(type_id)
