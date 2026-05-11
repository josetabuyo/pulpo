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
import re
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


def slugify(name: str) -> str:
    """Convierte nombre de contacto a slug kebab-case para nombre de carpeta.
    Ej: "Desarrollo SIGIRH  2025" → "desarrollo-sigirh-2025"
        "5491155612767"           → "5491155612767"  (sin cambio)
    """
    import unicodedata as _uc
    nfd = _uc.normalize("NFD", name)
    ascii_str = "".join(c for c in nfd if _uc.category(c) != "Mn")
    result = re.sub(r'[^a-z0-9]+', '-', ascii_str.lower()).strip('-')
    return result or "contacto"


def get_contact_display_name(empresa_id: str, slug: str) -> str | None:
    """Lee el nombre original almacenado en {slug}/name.txt, si existe."""
    name_file = _BASE / empresa_id / slug / "name.txt"
    if name_file.exists():
        return name_file.read_text(encoding="utf-8").strip()
    return None


def _path(empresa_id: str, contact_id: str) -> Path:
    """Retorna la ruta del chat.md del contacto.
    Nueva estructura: {empresa_id}/{slug}/chat.md
    Fallback (pre-migración): {empresa_id}/{contact_id}.md
    """
    slug = slugify(contact_id)
    new_p = _BASE / empresa_id / slug / "chat.md"
    # Si ya existe la nueva estructura, usarla
    if new_p.parent.exists():
        new_p.parent.mkdir(parents=True, exist_ok=True)
        return new_p
    # Fallback: estructura vieja (plana)
    old_p = _BASE / empresa_id / f"{contact_id}.md"
    if old_p.exists():
        return old_p
    # Default para escritura nueva: estructura nueva
    new_p.parent.mkdir(parents=True, exist_ok=True)
    return new_p


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


_MEDIA_PLACEHOLDER_RE = re.compile(
    r'^\[audio\s*[—–-]\s*sin blob\]|^\[audio\s*[—–-]\s*no disponible\]'
    r'|^\[audio\s*[—–-]\s*error\]|^\[audio\]$|^\[img:\]$|^\[media\]$'
    r'|^\[imagen(?:\s+guardada)?:'
    r'|^\[image:'
)


_NORMALIZE_IMAGEN_RE = re.compile(r'^\[imagen\s+guardada:', re.IGNORECASE)


def _normalize_body(body: str) -> str:
    """Normaliza variantes de imagen a forma canónica para dedup consistente.
    '[imagen guardada: X]' → '[imagen: X]'
    Esto evita duplicados entre entradas del scraper (guardada) y sync de DB (sin guardada).
    """
    return _NORMALIZE_IMAGEN_RE.sub('[imagen:', body.strip())


def _dedup_hash(ts: str, body: str) -> str:
    """Calcula el hash de dedup igual que accumulate(): content-only para media placeholder."""
    normalized = _normalize_body(body)
    is_media = bool(_MEDIA_PLACEHOLDER_RE.match(normalized))
    key = normalized if is_media else f"{ts}|{normalized}"
    return _hash(key)


def _ensure_loaded(empresa_id: str, contact_phone: str) -> set[str]:
    key = (empresa_id, contact_phone)
    if key not in _dedup_loaded:
        _dedup_loaded.add(key)
        _dedup[key] = set()
        p = _path(empresa_id, contact_phone)
        if p.exists():
            current_ts = ""
            current_body: str | None = None
            for line in p.read_text(encoding="utf-8").split("\n"):
                if line.startswith("## "):
                    # Nuevo bloque: hashear el anterior si estaba pendiente
                    if current_body is not None:
                        _dedup[key].add(_dedup_hash(current_ts, current_body))
                    current_ts = line[3:].strip()
                    current_body = None
                elif line.startswith("**["):
                    idx = line.find("** ")
                    if idx != -1:
                        current_body = line[idx + 3:]
                elif line.startswith("> ↩") and current_body is not None:
                    # Incluir la línea de reply en el body (igual que accumulate recibe)
                    current_body += "\n" + line
                elif line.strip() == "---" and current_body is not None:
                    _dedup[key].add(_dedup_hash(current_ts, current_body))
                    current_body = None
            # Último bloque sin "---"
            if current_body is not None:
                _dedup[key].add(_dedup_hash(current_ts, current_body))
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
    h = _dedup_hash(ts, content)
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
    """Retorna los identificadores de contactos.
    Nueva estructura: nombre de cada subdirectorio que contenga chat.md.
    Fallback: stem de .md planos (pre-migración).
    """
    d = _BASE / empresa_id
    if not d.exists():
        return []
    result = []
    seen_slugs: set[str] = set()
    # Nueva estructura: directorios con chat.md
    for sub in sorted(d.iterdir()):
        if sub.is_dir() and (sub / "chat.md").exists():
            result.append(sub.name)
            seen_slugs.add(sub.name)
    # Vieja estructura: .md planos no migrados aún
    for f in sorted(d.glob("*.md")):
        if f.name.endswith(".bak.md"):
            continue
        if slugify(f.stem) not in seen_slugs:
            result.append(f.stem)
    return result


def get_attachments_dir(empresa_id: str, contact_id: str) -> Path:
    """Carpeta para adjuntos del contacto. Nueva estructura: {slug}/ (mismo dir que chat.md)."""
    slug = slugify(contact_id)
    d = _BASE / empresa_id / slug
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


def trim_contact_from_date(empresa_id: str, contact_phone: str, cutoff_dt: datetime) -> None:
    """Recorta el .md conservando solo entradas anteriores a cutoff_dt. Backup en .bak.md."""
    p = _path(empresa_id, contact_phone)
    if not p.exists():
        return
    content = p.read_text(encoding="utf-8")
    bak = p.with_suffix(".bak.md")
    bak.write_text(content, encoding="utf-8")

    _TS_RE = re.compile(r'^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})')
    blocks = content.split("\n---\n")
    kept = []
    for block in blocks:
        block_stripped = block.strip()
        if not block_stripped:
            continue
        m = _TS_RE.search(block_stripped)
        if m:
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
                if ts < cutoff_dt:
                    kept.append(block_stripped)
            except ValueError:
                kept.append(block_stripped)
        else:
            kept.append(block_stripped)

    p.write_text("\n---\n".join(kept) + ("\n---\n" if kept else ""), encoding="utf-8")
    key = (empresa_id, contact_phone)
    _dedup_loaded.discard(key)
    _dedup.pop(key, None)


def clear_contact_full(empresa_id: str, contact_phone: str) -> None:
    """Full re-sync: borra el .md, el .bak.md y todos los adjuntos del contacto."""
    import shutil as _shutil
    src = _path(empresa_id, contact_phone)
    if src.exists():
        src.unlink()
    bak = src.with_suffix(".bak.md")
    if bak.exists():
        bak.unlink()
    att_dir = _BASE / empresa_id / contact_phone
    if att_dir.exists():
        _shutil.rmtree(att_dir)
    key = (empresa_id, contact_phone)
    _dedup_loaded.discard(key)
    _dedup.pop(key, None)


def _newest_message_ts(empresa_id: str, contact_phone: str) -> "datetime | None":
    """Retorna el datetime del mensaje más reciente en el .md, o None si vacío."""
    import re as _re
    p = _path(empresa_id, contact_phone)
    if not p.exists():
        return None
    newest = None
    _TS_RE = _re.compile(r'^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})')
    for line in p.read_text(encoding="utf-8").splitlines():
        m = _TS_RE.match(line)
        if m:
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
                if newest is None or ts > newest:
                    newest = ts
            except ValueError:
                pass
    return newest


def migrate_empresa_to_slugs(empresa_id: str) -> dict:
    """
    Migra la estructura vieja ({nombre}.md + {nombre}/) a la nueva ({slug}/chat.md).
    - Crea {slug}/chat.md copiando el .md original
    - Crea {slug}/name.txt con el nombre original (para display)
    - Mueve adjuntos de la carpeta vieja a {slug}/
    - Borra los archivos viejos si la copia fue exitosa
    Idempotente: skippea contactos ya migrados.
    """
    d = _BASE / empresa_id
    if not d.exists():
        return {"migrated": 0, "skipped": 0, "errors": []}

    migrated = 0
    skipped = 0
    errors = []

    for md_file in sorted(d.glob("*.md")):
        if md_file.name.endswith(".bak.md"):
            continue

        contact_id = md_file.stem
        slug = slugify(contact_id)
        slug_dir = d / slug
        target = slug_dir / "chat.md"

        try:
            slug_dir.mkdir(parents=True, exist_ok=True)

            # Guardar nombre original para display
            (slug_dir / "name.txt").write_text(contact_id, encoding="utf-8")

            if target.exists():
                # El slug dir ya empezó a acumular (backend reiniciado con nuevo código).
                # Prepender historial viejo al contenido nuevo para no perder mensajes.
                old_content = md_file.read_text(encoding="utf-8")
                new_content = target.read_text(encoding="utf-8")
                target.write_text(old_content + new_content, encoding="utf-8")
                # Invalidar dedup del slug para que re-lea el archivo combinado
                slug_key = (empresa_id, slug)
                _dedup_loaded.discard(slug_key)
                _dedup.pop(slug_key, None)
            else:
                # Copiar chat.md
                shutil.copy2(md_file, target)

            # Copiar bak si existe
            bak_src = md_file.with_suffix(".bak.md")
            if bak_src.exists():
                shutil.copy2(bak_src, slug_dir / "chat.bak.md")

            # Mover adjuntos de la carpeta vieja (si es distinta del slug_dir)
            old_att_dir = d / contact_id
            if (old_att_dir.exists()
                    and old_att_dir.is_dir()
                    and old_att_dir.resolve() != slug_dir.resolve()):
                for f in old_att_dir.iterdir():
                    dest = slug_dir / f.name
                    if not dest.exists():
                        shutil.copy2(f, dest)

            # Verificar que la copia fue exitosa antes de borrar
            if target.exists():
                md_file.unlink()
                if bak_src.exists():
                    bak_src.unlink()
                if (old_att_dir.exists()
                        and old_att_dir.is_dir()
                        and old_att_dir.resolve() != slug_dir.resolve()):
                    shutil.rmtree(old_att_dir)

            # Invalidar caché dedup
            key = (empresa_id, contact_id)
            _dedup_loaded.discard(key)
            _dedup.pop(key, None)

            migrated += 1
        except Exception as e:
            errors.append(f"{contact_id}: {e}")

    return {"empresa_id": empresa_id, "migrated": migrated, "skipped": skipped, "errors": errors}


class SummarizeNode(BaseNode):
    """
    Acumula el mensaje en el archivo .md del contacto.
    No produce reply — es un efecto de lado puro.
    Solo corre cuando from_poll=False (no previews del sidebar WA).

    Colocar en el flow DESPUÉS de transcribe_audio y save_attachment.
    Este nodo ya no maneja archivos — solo escribe texto al .md.
    """

    async def run(self, state: FlowState) -> FlowState:
        # Construir contenido: si hay adjunto guardado, registrarlo
        if state.attachment_path:
            from pathlib import Path as _Path
            fname = _Path(state.attachment_path).name
            content = state.message or f"[{state.message_type}: {fname}]"
        else:
            content = state.message

        if not content:
            return state

        # En mensajes de grupo con audio transcripto, prepender el remitente
        if state.group_sender and not content.startswith(state.group_sender):
            content = f"{state.group_sender}: {content}"

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
