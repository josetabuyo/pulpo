"""
SummarizeNode — acumula mensajes de un contacto en un archivo .md.
No produce reply. Solo registra para revisión posterior del operador.

Config: {} (sin configuración por ahora)

Lógica de dedup: al primer acceso por contacto carga los hashes de todos
los cuerpos ya escritos en el .md. accumulate() skippea si el mismo contenido
ya existe (previene duplicados por reinicios o syncs repetidos).
"""
import hashlib
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent.parent.parent.parent / "data" / "summaries"

# (empresa_id, contact_phone) → set de sha256(body) ya escritos
_dedup: dict[tuple[str, str], set[str]] = {}
_dedup_loaded: set[tuple[str, str]] = set()


def _path(empresa_id: str, contact_phone: str) -> Path:
    p = _BASE / empresa_id / f"{contact_phone}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _ensure_loaded(empresa_id: str, contact_phone: str) -> set[str]:
    key = (empresa_id, contact_phone)
    if key not in _dedup_loaded:
        _dedup_loaded.add(key)
        _dedup[key] = set()
        p = _path(empresa_id, contact_phone)
        if p.exists():
            current_ts = ""
            for line in p.read_text(encoding="utf-8").split("\n"):
                if line.startswith("## "):
                    current_ts = line[3:].strip()
                elif line.startswith("**["):
                    idx = line.find("** ")
                    if idx != -1:
                        body = line[idx + 3:]
                        _dedup[key].add(_hash(f"{current_ts}|{body}"))
    return _dedup[key]


def accumulate(
    empresa_id: str,
    contact_phone: str,
    contact_name: str,
    msg_type: str,
    content: str,
    timestamp: datetime | None = None,
) -> None:
    """Agrega una entrada al .md del contacto. Skippea si ya existe."""
    ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M")
    seen = _ensure_loaded(empresa_id, contact_phone)
    h = _hash(f"{ts}|{content}")
    if h in seen:
        return
    seen.add(h)
    entry = f"## {ts}\n**[{msg_type}]** {content}\n---\n"
    p = _path(empresa_id, contact_phone)
    with open(p, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.debug("[SummarizeNode] %s/%s — %d chars acumulados", empresa_id, contact_phone, len(content))


def get_summary(empresa_id: str, contact_phone: str) -> str | None:
    p = _path(empresa_id, contact_phone)
    return p.read_text(encoding="utf-8") if p.exists() else None


def list_contacts(empresa_id: str) -> list[str]:
    d = _BASE / empresa_id
    if not d.exists():
        return []
    return [f.stem for f in d.glob("*.md")]


def get_attachments_dir(empresa_id: str, contact_phone: str) -> Path:
    """Carpeta para adjuntos del contacto (junto al .md, mismo nombre sin extensión)."""
    d = _BASE / empresa_id / contact_phone
    d.mkdir(parents=True, exist_ok=True)
    return d


def clear_empresa(empresa_id: str) -> None:
    d = _BASE / empresa_id
    if not d.exists():
        return
    bak = _BASE / f"{empresa_id}.bak"
    if bak.exists():
        shutil.rmtree(bak)
    shutil.copytree(d, bak)
    for f in d.glob("*.md"):
        f.unlink()
    keys = [k for k in _dedup_loaded if k[0] == empresa_id]
    for k in keys:
        _dedup_loaded.discard(k)
        _dedup.pop(k, None)


def clear_contact(empresa_id: str, contact_phone: str) -> None:
    src = _path(empresa_id, contact_phone)
    if src.exists():
        bak = src.with_suffix(".bak.md")
        shutil.copy2(src, bak)
        src.unlink()
    key = (empresa_id, contact_phone)
    _dedup_loaded.discard(key)
    _dedup.pop(key, None)


class SummarizeNode(BaseNode):
    """
    Acumula el mensaje en el archivo .md del contacto.
    No produce reply — es un efecto de lado puro.
    Solo corre cuando from_poll=False (no previews del sidebar WA).

    Si state.attachment_path tiene un archivo temporal (imagen, documento),
    lo mueve a storage permanente antes de acumular.
    """

    async def run(self, state: FlowState) -> FlowState:
        if state.from_poll:
            return state

        content = state.message

        # Mover adjunto de ruta temporal a storage permanente
        if state.attachment_path:
            import shutil as _shutil
            from pathlib import Path as _Path
            src = _Path(state.attachment_path)
            if src.exists():
                att_dir = get_attachments_dir(state.empresa_id, state.contact_phone)
                dest = att_dir / src.name
                _shutil.move(str(src), str(dest))
                content = f"[{state.message_type}: {dest.name}]"

        accumulate(
            empresa_id=state.empresa_id,
            contact_phone=state.contact_phone,
            contact_name=state.contact_name,
            msg_type=state.message_type,
            content=content,
            timestamp=state.timestamp,
        )
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {}
