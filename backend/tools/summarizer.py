"""
Sumarizadora pasiva — acumula mensajes de un contacto en un archivo .md.
No envía respuestas, solo registra.

Dedup persistente: al primer acceso por contacto carga los hashes de todos
los bodies ya escritos en el .md. accumulate() skippea si el mismo contenido
ya existe (previene duplicados por restarts o full-sync repetidos).
"""
import hashlib
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent.parent.parent / "data" / "summaries"

# (empresa_id, contact_phone) -> set de sha256(body) ya escritos
_dedup: dict[tuple[str, str], set[str]] = {}
_dedup_loaded: set[tuple[str, str]] = set()


def _path(empresa_id: str, contact_phone: str) -> Path:
    p = _BASE / empresa_id / f"{contact_phone}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _ensure_loaded(empresa_id: str, contact_phone: str) -> set[str]:
    """Carga hashes del .md existente la primera vez. En memoria hasta restart."""
    key = (empresa_id, contact_phone)
    if key not in _dedup_loaded:
        _dedup_loaded.add(key)
        _dedup[key] = set()
        p = _path(empresa_id, contact_phone)
        if p.exists():
            current_ts = ""
            current_ts = ""
            for line in p.read_text(encoding="utf-8").split("\n"):
                if line.startswith("## "):
                    current_ts = line[3:].strip()
                elif line.startswith("**["):
                    idx = line.find("** ")
                    if idx != -1:
                        body = line[idx + 3:]
                        _dedup[key].add(_hash(f"{current_ts}|{body}"))
            logger.debug(
                "[summarizer] dedup cargado: %s/%s — %d entradas",
                empresa_id, contact_phone, len(_dedup[key])
            )
    return _dedup[key]


def accumulate(empresa_id: str, contact_phone: str, contact_name: str,
               msg_type: str, content: str, timestamp: datetime | None = None) -> None:
    """Agrega una entrada al archivo .md del contacto. Skippea si ya existe."""
    ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M")
    seen = _ensure_loaded(empresa_id, contact_phone)
    h = _hash(f"{ts}|{content}")
    if h in seen:
        logger.debug("[summarizer] dedup skip: %s/%s — ya registrado", empresa_id, contact_phone)
        return
    seen.add(h)
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


def clear_empresa(empresa_id: str) -> None:
    """Elimina todos los archivos .md de una empresa (para re-sync)."""
    d = _BASE / empresa_id
    if not d.exists():
        return
    for f in d.glob("*.md"):
        f.unlink()
    # Resetear dedup en memoria para esta empresa
    keys_to_remove = [k for k in _dedup_loaded if k[0] == empresa_id]
    for k in keys_to_remove:
        _dedup_loaded.discard(k)
        _dedup.pop(k, None)


def clear_contact(empresa_id: str, contact_phone: str) -> None:
    """Elimina el archivo .md de un contacto específico."""
    _path(empresa_id, contact_phone).unlink(missing_ok=True)
    key = (empresa_id, contact_phone)
    _dedup_loaded.discard(key)
    _dedup.pop(key, None)
