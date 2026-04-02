"""
Registro central de tipos de nodo para flows de agentes.

Un NodeType define todo lo necesario para representar un nodo:
  - id        → clave que viaja en el JSON entre backend y frontend
  - label     → nombre visible en la UI
  - color     → color del nodo en el grafo
  - description → texto del tooltip al hacer hover

Esta es la ÚNICA fuente de verdad. Ni el endpoint ni el frontend
hardcodean labels, colores ni descripciones.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeType:
    id: str
    label: str
    color: str
    description: str


NODE_TYPES: dict[str, NodeType] = {
    "start": NodeType(
        id="start",
        label="Inicio",
        color="#166534",
        description="Punto de entrada del agente. Recibe el mensaje del usuario.",
    ),
    "end": NodeType(
        id="end",
        label="Fin",
        color="#991b1b",
        description="Fin del flujo. La respuesta ya está lista para enviarse.",
    ),
    "router": NodeType(
        id="router",
        label="Router",
        color="#854d0e",
        description="Clasifica el mensaje y decide qué rama del flujo ejecutar.",
    ),
    "fetch": NodeType(
        id="fetch",
        label="Fetch",
        color="#1e40af",
        description="Consulta datos externos: Facebook, APIs o web scraping.",
    ),
    "llm": NodeType(
        id="llm",
        label="Asistente LLM",
        color="#6b21a8",
        description="Genera una respuesta usando un modelo de lenguaje (Groq / GPT).",
    ),
    "reply": NodeType(
        id="reply",
        label="Respuesta fija",
        color="#374151",
        description="Devuelve un mensaje predefinido sin procesamiento de IA.",
    ),
    "notify": NodeType(
        id="notify",
        label="Notificación",
        color="#9a3412",
        description="Envía una notificación a un trabajador o contacto externo.",
    ),
    "summarize": NodeType(
        id="summarize",
        label="Sumarizador",
        color="#14532d",
        description="Acumula mensajes del período y genera un resumen periódico.",
    ),
    "generic": NodeType(
        id="generic",
        label="Nodo",
        color="#1e293b",
        description="Nodo de procesamiento genérico.",
    ),
}

_FALLBACK = NODE_TYPES["generic"]


def get(type_id: str) -> NodeType:
    """Retorna el NodeType correspondiente, o generic si no existe."""
    return NODE_TYPES.get(type_id, _FALLBACK)


def classify(node_id: str) -> NodeType:
    """Infiere el NodeType a partir del nombre del nodo LangGraph."""
    if node_id == "__start__":
        return NODE_TYPES["start"]
    if node_id == "__end__":
        return NODE_TYPES["end"]
    if "router" in node_id or "classify" in node_id:
        return NODE_TYPES["router"]
    if "fetch" in node_id or "scrape" in node_id:
        return NODE_TYPES["fetch"]
    if ("noticias" in node_id or "llm" in node_id or "respond" in node_id
            or "assistant" in node_id or "generate" in node_id or "expand" in node_id):
        return NODE_TYPES["llm"]
    if "oficio" in node_id or "reply" in node_id or "fixed" in node_id:
        return NODE_TYPES["reply"]
    if "notify" in node_id:
        return NODE_TYPES["notify"]
    if "summar" in node_id:
        return NODE_TYPES["summarize"]
    return _FALLBACK
