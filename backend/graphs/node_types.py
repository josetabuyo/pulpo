"""
Registro central de tipos de nodo para flows de agentes.

Un NodeType define todo lo necesario para representar un nodo:
  - id          → clave que viaja en el JSON entre backend y frontend
  - label       → nombre visible en la UI
  - color       → color del nodo en el grafo
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
        label="Fetch externo",
        color="#1e40af",
        description="Consulta datos externos: Facebook, APIs o web scraping.",
    ),
    "search": NodeType(
        id="search",
        label="Búsqueda interna",
        color="#0f766e",
        description="Consulta fuentes internas: lista de oficios, auspiciantes, trabajadores.",
    ),
    "vector_search": NodeType(
        id="vector_search",
        label="Búsqueda vectorial",
        color="#0e7490",
        description="Busca en una colección vectorial (oficios, auspiciantes, etc.).",
    ),
    "send_message": NodeType(
        id="send_message",
        label="Enviar mensaje",
        color="#15803d",
        description="Envía un mensaje al usuario o a un contacto externo vía WA/TG.",
    ),
    "llm": NodeType(
        id="llm",
        label="Respuesta LLM",
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
    "llm_respond": NodeType(
        id="llm_respond",
        label="Respuesta LLM",
        color="#6b21a8",
        description="Genera una respuesta usando un modelo de lenguaje (Groq / Llama).",
    ),
    "luganense_flow": NodeType(
        id="luganense_flow",
        label="Flujo Luganense",
        color="#1e40af",
        description="Ejecuta el flujo completo de Luganense FC.",
    ),
    "message_trigger": NodeType(
        id="message_trigger",
        label="Trigger de mensaje",
        color="#166534",
        description="Punto de entrada del flow. Filtra por conexión, contacto y patrón de mensaje.",
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
    """
    Infiere el NodeType a partir del nombre del nodo LangGraph.
    Convención de nombres:
      scope_router, *_router   → router
      fetch_*                  → fetch  (externo)
      buscar_*_fb / *_facebook → fetch  (externo)
      buscar_*                 → search (interno)
      expandir_*, *_expand     → llm
      responder_*, *_respond   → llm
      *_llm, *_noticias        → llm
      notificar_*, *_notify    → notify
      *_summar*                → summarize
    """
    if node_id == "__start__":
        return NODE_TYPES["start"]
    if node_id == "__end__":
        return NODE_TYPES["end"]
    if "router" in node_id or "classify" in node_id:
        return NODE_TYPES["router"]
    # fetch externo antes que búsqueda interna
    if "fetch" in node_id or "scrape" in node_id or "obtener" in node_id:
        return NODE_TYPES["fetch"]
    if "buscar" in node_id:
        if "fb" in node_id or "facebook" in node_id or "post" in node_id:
            return NODE_TYPES["fetch"]
        return NODE_TYPES["vector_search"]
    if ("expandir" in node_id or "expand" in node_id
            or "responder" in node_id or "respond" in node_id
            or "generar" in node_id or "generate" in node_id
            or "noticias" in node_id or "llm" in node_id
            or "assistant" in node_id):
        return NODE_TYPES["llm"]
    if "notificar" in node_id or "notify" in node_id:
        return NODE_TYPES["send_message"]
    if "summar" in node_id:
        return NODE_TYPES["summarize"]
    if "reply" in node_id or "fixed" in node_id:
        return NODE_TYPES["reply"]
    return _FALLBACK
