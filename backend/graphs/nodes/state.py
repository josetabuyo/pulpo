"""
FlowState — estado que viaja por los nodos de un flow.

Cada adapter (Telegram, Wavi, Sim) normaliza el mensaje entrante
a un FlowState antes de pasarlo al engine. Los nodos lo leen y
modifican; el adapter lee el resultado y envía la respuesta.

⚠️ contact_phone es el identificador del contacto EN SU CANAL, no siempre
un teléfono:
  - telegram → chat_id numérico
  - wavi     → display name del contacto (check-updates no expone números)
  - sim      → teléfono simulado
Filtros, cooldowns y summaries se indexan por este valor; el teléfono real
(si se conoce) vive en contact_channels de la DB.
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
    connection_id: str = ""             # ID de la conexión (session TG) que recibió el mensaje
    bot_name: str = ""
    empresa_id: str = ""
    contact_phone: str = ""            # ID del contacto en su canal (ver docstring del módulo)
    contact_name: str = ""
    canal: str = "telegram"            # telegram | wavi | (sim usa telegram)

    # ── Flags de transporte ───────────────────────────────────────
    from_poll: bool = False            # True = preview del sidebar, no acumular ni responder
    from_delta_sync: bool = False      # True = sync histórico, acumular pero no responder
    timestamp: Optional[datetime] = None  # timestamp real del mensaje (útil en delta-sync)

    # ── Estado inter-nodo (producido y consumido por nodos intermedios) ─────────
    route: str = ""                    # router node setea esto; engine sigue solo edges con ese label
    context: str = ""                  # texto acumulado de fetch/search/llm para el siguiente nodo
    query: str = ""                    # query expandida (llm output=query → fetch/search la lee)
    fb_posts: list = field(default_factory=list)  # posts de Facebook con text + url
    vars: dict = field(default_factory=dict)       # valores arbitrarios: nodos escriben, placeholders leen

    # ── Metadatos de grupo ────────────────────────────────────────
    group_sender: str = ""              # en grupos: nombre del miembro que envió (vacío fuera de grupos)

    # ── Salida (producida por nodos) ──────────────────────────────
    reply: Optional[str] = None
