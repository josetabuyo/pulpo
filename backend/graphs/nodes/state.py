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
    bot_name: str = ""
    empresa_id: str = ""
    contact_phone: str = ""
    contact_name: str = ""
    canal: str = "whatsapp"            # whatsapp / telegram

    # ── Flags de transporte ───────────────────────────────────────
    from_poll: bool = False            # True = preview del sidebar WA, no acumular ni responder
    from_delta_sync: bool = False      # True = sync histórico, acumular pero no responder
    timestamp: Optional[datetime] = None  # timestamp real del mensaje (útil en delta-sync)

    # ── Salida (producida por nodos) ──────────────────────────────
    reply: Optional[str] = None
    image_url: Optional[str] = None
