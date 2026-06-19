"""
API para consultar los resúmenes acumulados por la herramienta sumarizadora.
"""
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse, FileResponse
from sqlalchemy import text
from db import AsyncSessionLocal
from middleware_auth import get_bot_id_from_token
from api.deps import ADMIN_PASSWORD
from graphs.nodes.summarize import (
    get_summary, list_contacts, clear_bot, clear_contact, accumulate,
    clear_contact_full, _newest_message_ts, trim_contact_from_date,
    migrate_bot_to_slugs, get_contact_display_name,
    delete_message_by_id, rewrite_chat, consolidate_contact, get_consolidation_meta,
    get_consolidation_dir,
    _path as _summary_path,
)

# Módulo de compatibilidad — expone las mismas funciones que el viejo tools/summarizer
class summarizer:
    get_summary = staticmethod(get_summary)
    list_contacts = staticmethod(list_contacts)
    clear_bot = staticmethod(clear_bot)
    clear_contact = staticmethod(clear_contact)
    accumulate = staticmethod(accumulate)
from fastapi import Request, Header

router = APIRouter()

_ADMIN_SENTINEL = "__admin__"


def _db_phone(bot_id: str, contact_id: str) -> str:
    """Para contactos migrados a slug, resuelve el phone real para queries a DB.
    Lee name.txt del slug dir. Si no existe, devuelve contact_id tal cual.
    """
    return get_contact_display_name(bot_id, contact_id) or contact_id


def _require_bot_or_admin(request: Request, x_password: str = Header(default=None)) -> str:
    if x_password == ADMIN_PASSWORD:
        return _ADMIN_SENTINEL
    bot_id = get_bot_id_from_token(request)
    if not bot_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return bot_id


def _check_auth(bot_id: str, token_bot_id: str = Depends(_require_bot_or_admin)) -> str:
    if token_bot_id != _ADMIN_SENTINEL and token_bot_id != bot_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta bot")
    return token_bot_id


@router.get("/summarizer/{bot_id}")
async def list_summaries(bot_id: str, _: str = Depends(_check_auth)):
    """Lista los contactos que tienen resumen acumulado, con nombre si está en la agenda."""
    phones = summarizer.list_contacts(bot_id)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(
                "SELECT cc.value, c.name FROM contact_channels cc "
                "JOIN contacts c ON cc.contact_id = c.id "
                "WHERE c.bot_id = :eid AND cc.type = 'telegram'"
            ),
            {"eid": bot_id},
        )).fetchall()
    phone_to_name = {r[0]: r[1] for r in rows}
    from graphs.nodes.summarize import _BASE
    contacts = []
    for p in phones:
        # Prioridad: DB por phone > name.txt (nombre original pre-slug) > slug mismo
        name = phone_to_name.get(p) or get_contact_display_name(bot_id, p) or p
        contacts.append({"phone": p, "name": name})
    return {
        "contacts": contacts,
        "path": str(_BASE / bot_id),
    }


@router.get("/summarizer/{bot_id}/consolidations")
async def list_consolidations(bot_id: str, _: str = Depends(_check_auth)):
    """Metadata de consolidaciones de todos los contactos de la bot."""
    contacts_list = summarizer.list_contacts(bot_id)
    result = []
    for phone in contacts_list:
        meta = get_consolidation_meta(bot_id, phone)
        if meta:
            cdir = get_consolidation_dir(bot_id, phone)
            result.append({
                "phone": phone,
                "name": get_contact_display_name(bot_id, phone) or phone,
                "consolidated_at": meta.get("consolidated_at"),
                "last_message_ts": meta.get("last_message_ts"),
                "message_count": meta.get("message_count", 0),
                "path": str(cdir / "chat.md") if cdir else "",
            })
    return {"consolidations": result}


@router.get("/summarizer/{bot_id}/{contact_phone}", response_class=PlainTextResponse)
async def get_summary(bot_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """Devuelve el resumen acumulado de un contacto como texto plano (Markdown)."""
    content = summarizer.get_summary(bot_id, contact_phone)
    if content is None:
        raise HTTPException(status_code=404, detail="Sin resumen para este contacto")
    return content


# ─── Helpers de parseo ──────────────────────────────────────────────────────

def _parse_messages(md_content: str, bot_id: str, contact_phone: str, owner_names: set[str] | None = None, keep_ids: bool = False) -> list[dict]:
    """Convierte el .md acumulado en lista de mensajes estructurados."""
    messages = []
    blocks = re.split(r'\n---\n', md_content)

    # Dedup unificado: content → (index_en_messages, tipo)
    # Permite que [audio] reemplace un [text] previo con el mismo contenido
    # (el audio viene del scraper y es más rico; el texto viene del sync de DB)
    _seen: dict[str, tuple[int, str]] = {}

    # Dedup temporal: content → último timestamp ISO visto
    # Evita duplicados UTC/local: mismo texto dentro de ±4h se trata como el mismo mensaje
    _seen_ts: dict[str, str] = {}
    _4H = 4 * 3600  # segundos
    _owners = owner_names or set()

    def _dir(sender: str | None) -> str:
        return "out" if sender and sender in _owners else "in"

    _id_re = re.compile(r'\[id:([\d.]+)\]')

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        timestamp_str = None
        msg_id: str | None = None
        msg_line = None
        extra_lines: list[str] = []
        reply_to = None

        for line in block.split("\n"):
            if line.startswith("## "):
                header = line[3:].strip()
                id_m = _id_re.search(header)
                msg_id = id_m.group(1) if id_m else None
                timestamp_str = _id_re.sub("", header).strip()
                msg_line = None
                extra_lines = []
            elif line.startswith("**["):
                msg_line = line
                extra_lines = []
            elif line.startswith("> ↩"):
                # Línea de cita/respuesta: "> ↩ texto citado"
                reply_to = line[3:].strip()  # Quita "> ↩" y espacios
            elif msg_line is not None and line.strip():
                # Línea de continuación de un mensaje multi-línea
                extra_lines.append(line)

        if not msg_line:
            continue

        # Combinar línea principal con las de continuación
        if extra_lines:
            msg_line = msg_line + "\n" + "\n".join(extra_lines)

        m = re.match(r'\*\*\[([^\]]+)\]\*\*\s*(.*)', msg_line, re.DOTALL)
        if not m:
            continue

        type_info = m.group(1).strip()
        content = m.group(2).strip()

        ts_iso = None
        if timestamp_str:
            for _fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    ts_iso = datetime.strptime(timestamp_str, _fmt).isoformat()
                    break
                except ValueError:
                    continue
            else:
                ts_iso = timestamp_str

        if type_info in ("image", "imagen"):
            img_sender = None
            img_name = None
            img_caption = None
            # Extraer sender si hay "Nombre: " prefix
            gs = re.match(r'^([^\[:]{2,40}):\s+(.*)', content, re.DOTALL)
            if gs:
                img_sender = gs.group(1).strip()
                remainder = gs.group(2).strip()
            else:
                remainder = content
            # Extraer filename y caption opcional: "[imagen guardada: file.jpg] — caption"
            img_m = re.match(r'\[imagen(?:\s*guardada)?:\s*([^\]]+)\](?:\s*[—–-]\s*(.+))?', remainder, re.DOTALL)
            if img_m:
                img_name = img_m.group(1).strip()
                if img_m.group(2):
                    img_caption = img_m.group(2).strip()
            else:
                img_name = remainder
            messages.append({
                "type": "image",
                "_id": msg_id,
                "direction": _dir(img_sender),
                "timestamp": ts_iso,
                "sender": img_sender,
                "filename": img_name,
                "caption": img_caption,
                "reply_to": reply_to,
            })
        elif type_info.startswith("audio"):
            duration = type_info[5:].strip()
            t_match = re.match(r'_transcripción:_\s*(.*)', content, re.DOTALL)
            transcription = t_match.group(1).strip() if t_match else content
            # Parsear "Nombre: texto" de la transcripción
            audio_sender = None
            g = re.match(r'^([^:]{2,40}):\s+(.*)', transcription, re.DOTALL)
            if g:
                audio_sender = g.group(1).strip()
                transcription = g.group(2).strip()
            audio_msg = {
                "type": "audio",
                "_id": msg_id,
                "direction": _dir(audio_sender),
                "timestamp": ts_iso,
                "duration": duration,
                "sender": audio_sender,
                "transcription": transcription,
                "reply_to": reply_to,
            }
            norm = transcription
            if norm in _seen:
                idx, prev_type = _seen[norm]
                if prev_type == "text":
                    # Reemplazar el [text] con este [audio] más rico
                    messages[idx] = audio_msg
                    _seen[norm] = (idx, "audio")
                # Si ya era audio: skip
                continue
            _seen[norm] = (len(messages), "audio")
            messages.append(audio_msg)
        elif type_info in ("documento", "document"):
            f_match = re.match(r'`([^`]+)`\s*\(([^)]+)\)', content)
            if f_match:
                filename = f_match.group(1)
                size = f_match.group(2)
            else:
                filename = content
                size = ""
            # Documentos no tienen sender explícito — asumimos "in" por defecto
            messages.append({
                "type": "document",
                "_id": msg_id,
                "direction": "in",
                "timestamp": ts_iso,
                "filename": filename,
                "size": size,
                "download_url": f"/api/summarizer/{bot_id}/{contact_phone}/docs/{filename}",
                "reply_to": reply_to,
            })
        else:
            # Detectar "Nombre: contenido" en mensajes de grupo
            sender = None
            text_content = content
            g = re.match(r'^([^:]{2,40}):\s+(.*)', content, re.DOTALL)
            if g:
                sender = g.group(1).strip()
                text_content = g.group(2).strip()
            # Dedup por contenido largo (audio/text mismo cuerpo)
            norm = text_content
            if len(norm) > 40:
                if norm in _seen:
                    continue
                _seen[norm] = (len(messages), "text")
            # Dedup temporal: mismo contenido dentro de ±4h → duplicado UTC/local
            if ts_iso and norm in _seen_ts:
                try:
                    from datetime import datetime as _dt2
                    prev = _dt2.fromisoformat(_seen_ts[norm])
                    curr = _dt2.fromisoformat(ts_iso)
                    if abs((curr - prev).total_seconds()) <= _4H:
                        continue
                except (ValueError, TypeError):
                    pass
            if ts_iso:
                _seen_ts[norm] = ts_iso
            messages.append({
                "type": "text",
                "_id": msg_id,
                "direction": _dir(sender),
                "timestamp": ts_iso,
                "sender": sender,
                "content": text_content,
                "reply_to": reply_to,
            })

    # Ordenar por ID jerárquico cuando hay IDs presentes (inserción en el medio funciona correctamente)
    if any(m.get("_id") for m in messages):
        from graphs.nodes.summarize import _id_sort_key
        messages.sort(key=lambda m: _id_sort_key(m.get("_id") or "0"))
    if not keep_ids:
        for m in messages:
            m.pop("_id", None)
    return messages


# ─── Endpoints de mensajes y adjuntos ───────────────────────────────────────

@router.get("/summarizer/{bot_id}/{contact_phone}/messages")
async def get_messages(
    bot_id: str,
    contact_phone: str,
    include_ids: bool = Query(default=False),
    _: str = Depends(_check_auth),
):
    """Devuelve los mensajes del resumen en el orden del archivo (incluye reordenamientos manuales)."""
    content = summarizer.get_summary(bot_id, contact_phone)
    if content is None:
        raise HTTPException(status_code=404, detail="Sin resumen para este contacto")

    owner_names: set[str] = {"Tú"}

    messages = _parse_messages(content, bot_id, contact_phone, owner_names, keep_ids=include_ids)
    p = _summary_path(bot_id, contact_phone)
    version = int(p.stat().st_mtime * 1000) if p.exists() else 0
    return {"messages": messages, "version": version}



import re as _re_sum

_SKIP_EXACT = {"Foto", "GIF", "Video", "Imagen", "Sticker", "Se eliminó este mensaje."}
_SKIP_CONTAINS = ["[audio", "audio — sin blob", "audio — no disponible", "audio — error",
                  "también está en este grupo", "también está en este grupo.",
                  "se unió al grupo", "fue añadido al grupo", "fue eliminado del grupo",
                  "abandonó el grupo", "joined using this group", "was added", "left"]
# "Fabian está grabando un audio…" y similares
_SKIP_ENDSWITH = ["está grabando un audio…", "está grabando un audio...", "is recording an audio"]

def _is_useful(body: str) -> bool:
    if not body or len(body.strip()) < 3:
        return False
    b = body.strip()
    if b in _SKIP_EXACT:
        return False
    # Duraciones de audio crudas de la DB (ej: "1:55", "0:37") — no son texto real
    if _re_sum.match(r'^\d{1,2}:\d{2}$', b):
        return False
    # Indicadores de typing ("X está grabando un audio…")
    if any(b.lower().endswith(s.lower()) for s in _SKIP_ENDSWITH):
        return False
    return not any(p.lower() in b.lower() for p in _SKIP_CONTAINS)


@router.post("/summarizer/{bot_id}/{contact_phone}/sync")
async def sync_contact(bot_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """
    FUENTE: DB (no WA Web).
    Reconstruye el .md de un contacto a partir de los mensajes ya guardados en base de datos.
    Solo incluye mensajes entrantes (outbound=0). Para scrape desde WA Web usar /full-resync.
    """
    summarizer.clear_contact(bot_id, contact_phone)

    phone_for_db = _db_phone(bot_id, contact_phone)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(
                "SELECT body, timestamp FROM messages "
                "WHERE connection_id = :eid AND outbound = 0 AND phone = :phone "
                "ORDER BY timestamp ASC"
            ),
            {"eid": bot_id, "phone": phone_for_db},
        )).fetchall()

    synced = 0
    for body, ts_raw in rows:
        if not _is_useful(body):
            continue
        # Saltear entradas sin timestamp — son artefactos de restarts, no mensajes reales
        if not ts_raw:
            continue
        ts = None
        try:
            ts = datetime.fromisoformat(str(ts_raw))
        except ValueError:
            pass
        summarizer.accumulate(
            bot_id=bot_id,
            contact_phone=contact_phone,
            contact_name=phone_for_db,
            msg_type="text",
            content=f"{phone_for_db}: {body.strip()}",
            timestamp=ts,
        )
        synced += 1

    return {"synced": synced}


@router.post("/summarizer/{bot_id}/migrate-to-slugs")
async def migrate_to_slugs(bot_id: str, _: str = Depends(_check_auth)):
    """Migra la estructura vieja ({nombre}.md) a la nueva ({slug}/chat.md). Idempotente."""
    result = migrate_bot_to_slugs(bot_id)
    return result


@router.post("/summarizer/{bot_id}/sync-all")
async def sync_all_contacts(
    bot_id: str,
    from_date: str = Query(default=None),
    _: str = Depends(_check_auth),
):
    """
    FUENTE: DB (no WA Web).
    Reconstruye el .md de los contactos registrados de una bot a partir de la base de datos.
    Solo incluye mensajes entrantes (outbound=0). Para scrape desde WA Web usar /full-resync.

    Si from_date (YYYY-MM-DD): trim del .md desde esa fecha + re-procesa solo esos mensajes.
    Sin from_date: rebuild completo desde cero.

    SEGURIDAD: solo procesa phones que están en contact_channels para la bot.
    Nunca procesa el universo completo de la tabla messages, que incluye grupos,
    números desconocidos y cualquier cosa que haya mandado un mensaje alguna vez.
    """
    cutoff_dt = None
    if from_date:
        try:
            cutoff_dt = datetime.fromisoformat(from_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="from_date inválido, usar YYYY-MM-DD")

    results = []

    async with AsyncSessionLocal() as session:
        # Fuente de verdad: solo contactos registrados en contact_channels para esta bot.
        # Esto garantiza que sync-all solo opera sobre contactos explícitamente creados,
        # nunca sobre el universo abierto de mensajes recibidos.
        channel_rows = (await session.execute(
            text(
                "SELECT DISTINCT cc.value FROM contact_channels cc "
                "JOIN contacts c ON c.id = cc.contact_id "
                "WHERE c.bot_id = :eid AND cc.type = 'telegram'"
            ),
            {"eid": bot_id},
        )).fetchall()

        phones = [r[0] for r in channel_rows if r[0]]

        for phone in phones:
            if cutoff_dt:
                trim_contact_from_date(bot_id, phone, cutoff_dt)
                rows = (await session.execute(
                    text(
                        "SELECT body, timestamp FROM messages "
                        "WHERE connection_id = :eid AND outbound = 0 AND phone = :phone "
                        "AND timestamp >= :cutoff ORDER BY timestamp ASC"
                    ),
                    {"eid": bot_id, "phone": phone, "cutoff": from_date},
                )).fetchall()
            else:
                summarizer.clear_contact(bot_id, phone)
                rows = (await session.execute(
                    text(
                        "SELECT body, timestamp FROM messages "
                        "WHERE connection_id = :eid AND outbound = 0 AND phone = :phone "
                        "ORDER BY timestamp ASC"
                    ),
                    {"eid": bot_id, "phone": phone},
                )).fetchall()

            contact_display = _db_phone(bot_id, phone)
            synced = 0
            for body, ts_raw in rows:
                if not _is_useful(body):
                    continue
                if not ts_raw:
                    continue
                ts = None
                try:
                    ts = datetime.fromisoformat(str(ts_raw))
                except ValueError:
                    pass
                summarizer.accumulate(
                    bot_id=bot_id,
                    contact_phone=phone,
                    contact_name=contact_display,
                    msg_type="text",
                    content=f"{contact_display}: {body.strip()}",
                    timestamp=ts,
                )
                synced += 1
            results.append({"phone": phone, "synced": synced})

    return {"contacts": len(phones), "details": results}


@router.get("/summarizer/{bot_id}/{contact_phone}/docs/{filename}")
async def download_attachment(
    bot_id: str, contact_phone: str, filename: str,
    _: str = Depends(_check_auth),
):
    """Descarga un adjunto del contacto."""
    from graphs.nodes.summarize import get_attachments_dir
    attachments_dir = get_attachments_dir(bot_id, contact_phone)
    file_path = attachments_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/summarizer/{bot_id}/backup-and-clean")
async def backup_and_clean(bot_id: str, _: str = Depends(_check_auth)):
    """
    Hace backup de todos los chat.md de la bot (→ chat.bak.md) y los borra.
    El summarize sigue acumulando desde cero a partir del próximo mensaje.
    """
    import shutil as _shutil
    from graphs.nodes.summarize import _BASE, slugify
    bot_dir = _BASE / bot_id
    backed_up = 0
    if bot_dir.exists():
        for md_file in bot_dir.rglob("chat.md"):
            bak = md_file.with_name("chat.bak.md")
            _shutil.copy2(md_file, bak)
            md_file.unlink()
            backed_up += 1
    # Invalidar dedup en memoria
    from graphs.nodes.summarize import invalidate_dedup
    invalidate_dedup(bot_id)
    return {"backed_up": backed_up, "path": str(bot_dir)}


@router.get("/summarizer/{bot_id}/download")
async def download_summaries(bot_id: str, _: str = Depends(_check_auth)):
    """Descarga todos los resúmenes de la bot como un archivo ZIP."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    from graphs.nodes.summarize import _BASE
    bot_dir = _BASE / bot_id
    if not bot_dir.exists():
        raise HTTPException(status_code=404, detail="No hay resúmenes para esta bot")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for md_file in bot_dir.rglob("*.md"):
            zf.write(md_file, md_file.relative_to(bot_dir))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="summaries_{bot_id}.zip"'},
    )


# ─── Endpoints de manual tuning ─────────────────────────────────────────────

from fastapi import UploadFile, File as FastAPIFile
import uuid as _uuid
from pydantic import BaseModel


@router.post("/summarizer/{bot_id}/{contact_phone}/upload-image")
async def upload_image(
    bot_id: str,
    contact_phone: str,
    file: UploadFile = FastAPIFile(...),
    _: str = Depends(_check_auth),
):
    """Sube una imagen al directorio de adjuntos del contacto. Devuelve {filename}."""
    from graphs.nodes.summarize import get_attachments_dir
    attachments_dir = get_attachments_dir(bot_id, contact_phone)
    raw_ext = Path(file.filename).suffix.lower() if file.filename and "." in file.filename else ".png"
    ext = raw_ext if raw_ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ".png"
    filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_uuid.uuid4().hex[:6]}{ext}"
    content = await file.read()
    (attachments_dir / filename).write_bytes(content)
    return {"ok": True, "filename": filename}


class InsertMessageBody(BaseModel):
    type: str = "text"
    sender: str | None = None
    content: str
    timestamp: str | None = None


class RewriteMessagesBody(BaseModel):
    messages: list[dict]
    version: int | None = None


@router.post("/summarizer/{bot_id}/{contact_phone}/message")
async def insert_message(
    bot_id: str,
    contact_phone: str,
    body: InsertMessageBody,
    _: str = Depends(_check_auth),
):
    """Inserta un mensaje nuevo en el chat.md (append al final o con timestamp dado)."""
    ts = None
    if body.timestamp:
        try:
            ts = datetime.fromisoformat(body.timestamp)
        except ValueError:
            pass

    content_str = body.content
    if body.sender:
        content_str = f"{body.sender}: {body.content}"

    contact_name = get_contact_display_name(bot_id, contact_phone) or contact_phone
    accumulate(
        bot_id=bot_id,
        contact_phone=contact_phone,
        contact_name=contact_name,
        msg_type=body.type,
        content=content_str,
        timestamp=ts,
    )

    from graphs.nodes.summarize import _path as _p, _read_entries_meta
    p = _p(bot_id, contact_phone)
    count = 0
    if p.exists():
        count = sum(1 for b in p.read_text(encoding="utf-8").split("\n---\n") if b.strip().startswith("## "))
    return {"ok": True, "message_count": count}


@router.delete("/summarizer/{bot_id}/{contact_phone}/message/{msg_id}")
async def delete_message(
    bot_id: str,
    contact_phone: str,
    msg_id: str,
    _: str = Depends(_check_auth),
):
    """Elimina un mensaje del chat.md por su ID."""
    found = delete_message_by_id(bot_id, contact_phone, msg_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Mensaje {msg_id} no encontrado")
    return {"ok": True}


@router.put("/summarizer/{bot_id}/{contact_phone}/messages")
async def rewrite_messages(
    bot_id: str,
    contact_phone: str,
    body: RewriteMessagesBody,
    _: str = Depends(_check_auth),
):
    """Reescribe el chat.md completo con la lista de mensajes ordenada."""
    if body.version is not None:
        p_check = _summary_path(bot_id, contact_phone)
        current_v = int(p_check.stat().st_mtime * 1000) if p_check.exists() else 0
        if current_v != body.version:
            raise HTTPException(status_code=409, detail="Conflicto: el resumen fue modificado por otro proceso")
    rewrite_chat(bot_id, contact_phone, body.messages)
    p = _summary_path(bot_id, contact_phone)
    count = 0
    version = 0
    if p.exists():
        count = sum(1 for b in p.read_text(encoding="utf-8").split("\n---\n") if b.strip().startswith("## "))
        version = int(p.stat().st_mtime * 1000)
    return {"ok": True, "message_count": count, "version": version}


@router.post("/summarizer/{bot_id}/{contact_phone}/consolidate")
async def consolidate(
    bot_id: str,
    contact_phone: str,
    _: str = Depends(_check_auth),
):
    """Consolida el historial actual: copia chat.md a consolidated/ y guarda metadata."""
    meta = consolidate_contact(bot_id, contact_phone)
    return {"ok": True, **meta}


@router.get("/summarizer/{bot_id}/{contact_phone}/consolidation")
async def get_consolidation(
    bot_id: str,
    contact_phone: str,
    _: str = Depends(_check_auth),
):
    """Retorna metadata de la última consolidación, o 404 si no hay ninguna."""
    meta = get_consolidation_meta(bot_id, contact_phone)
    if meta is None:
        raise HTTPException(status_code=404, detail="Sin consolidación para este contacto")
    return meta
