"""
Sumarizadora pasiva — acumula mensajes de un contacto en un archivo .md.
No envía respuestas, solo registra.
"""
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent.parent.parent / "data" / "summaries"


def _path(empresa_id: str, contact_phone: str) -> Path:
    p = _BASE / empresa_id / f"{contact_phone}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def accumulate(empresa_id: str, contact_phone: str, contact_name: str,
               msg_type: str, content: str, timestamp: datetime | None = None) -> None:
    """Agrega una entrada al archivo .md del contacto."""
    ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M")
    entry = f"## {ts}\n**[{msg_type}]** {content}\n---\n"
    p = _path(empresa_id, contact_phone)
    with open(p, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.debug("[summarizer] %s/%s — %s chars acumulados", empresa_id, contact_phone, len(content))


def get_summary(empresa_id: str, contact_phone: str) -> str | None:
    """Retorna el contenido del .md o None si no existe."""
    p = _path(empresa_id, contact_phone)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def list_contacts(empresa_id: str) -> list[str]:
    """Lista los teléfonos que tienen resumen para esta empresa."""
    d = _BASE / empresa_id
    if not d.exists():
        return []
    return [f.stem for f in d.glob("*.md")]
