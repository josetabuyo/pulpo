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

── State de nodos ────────────────────────────────────────────────────────────
Todo lo que los nodos producen y consumen vive en `data: dict`.
No hay campos separados para context, query, route, reply, vars, etc.
Cada nodo escribe en la clave que corresponde al negocio que resuelve.

Claves con semántica reservada por el engine:
  data["reply"]    → respuesta saliente (el adapter la envía al usuario)
  data["route"]    → decisión del RouterNode (el engine sigue el edge con ese label)
  data["context"]  → clave default para contexto de LLM (configurable en cada nodo)
  data["query"]    → clave default para query expandida (configurable en cada nodo)
  data["fb_posts"] → posts de Facebook (FetchNode los deja acá)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FlowState:
    # ── Entrada (inmutable — la setea el adapter antes de entrar al engine) ──
    message: str
    message_type: str = "text"         # text / audio / image / document
    attachment_path: Optional[str] = None  # ruta a adjunto descargado (imagen, doc)

    # ── Contexto de la conversación ───────────────────────────────────────────
    connection_id: str = ""
    bot_name: str = ""
    bot_id: str = ""
    contact_phone: str = ""            # ID del contacto en su canal (ver docstring del módulo)
    contact_name: str = ""
    canal: str = "telegram"            # telegram | wavi | (sim usa telegram)

    # ── Flags de transporte ───────────────────────────────────────────────────
    from_poll: bool = False            # True = preview del sidebar, no acumular ni responder
    from_delta_sync: bool = False      # True = sync histórico, acumular pero no responder
    timestamp: Optional[datetime] = None  # timestamp real del mensaje (útil en delta-sync)

    # ── Metadatos de grupo ────────────────────────────────────────────────────
    group_sender: str = ""             # en grupos: nombre del miembro que envió

    # ── Estado de flujo — todo lo que los nodos producen y consumen ───────────
    data: dict = field(default_factory=dict)
