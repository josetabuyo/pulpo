"""
FlowState — estado que viaja por los nodos de un flow.

Cada adapter (WA, Telegram, Sim) normaliza el mensaje entrante
a un FlowState antes de pasarlo al engine. Los nodos lo leen y
modifican; el adapter lee el resultado y envía la respuesta.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FlowState:
    # ── Entrada ──────────────────────────────────────────────────
    message: str                       # texto ya procesado (audio transcripto, etc.)
    message_type: str = "text"         # text / audio / image / document
    attachment_path: Optional[str] = None  # ruta a adjunto descargado (imagen, doc)

    # ── Contexto de la conversación ───────────────────────────────
    connection_id: str = ""             # ID de la conexión (número WA o session TG) que recibió el mensaje
    bot_name: str = ""
    empresa_id: str = ""
    contact_phone: str = ""
    contact_name: str = ""
    canal: str = "whatsapp"            # whatsapp / telegram

    # ── Flags de transporte ───────────────────────────────────────
    from_poll: bool = False            # True = preview del sidebar WA, no acumular ni responder
    from_delta_sync: bool = False      # True = sync histórico, acumular pero no responder
    timestamp: Optional[datetime] = None  # timestamp real del mensaje (útil en delta-sync)

    # ── Estado inter-nodo (producido y consumido por nodos intermedios) ─────────
    route: str = ""                    # router node setea esto; engine sigue solo edges con ese label
    context: str = ""                  # texto acumulado de fetch/search/llm para el siguiente nodo
    query: str = ""                    # query expandida (llm output=query → fetch/search la lee)
    fb_posts: list = field(default_factory=list)  # posts de Facebook con text + image_url

    # ── Salida (producida por nodos) ──────────────────────────────
    reply: Optional[str] = None
    image_url: Optional[str] = None
