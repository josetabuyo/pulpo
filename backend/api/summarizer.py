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
from middleware_auth import get_empresa_id_from_token
from api.deps import ADMIN_PASSWORD
from graphs.nodes.summarize import (
    get_summary, list_contacts, clear_empresa, clear_contact, accumulate,
    clear_contact_full, _newest_message_ts, trim_contact_from_date,
    migrate_empresa_to_slugs, get_contact_display_name,
)

# Módulo de compatibilidad — expone las mismas funciones que el viejo tools/summarizer
class summarizer:
    get_summary = staticmethod(get_summary)
    list_contacts = staticmethod(list_contacts)
    clear_empresa = staticmethod(clear_empresa)
    clear_contact = staticmethod(clear_contact)
    accumulate = staticmethod(accumulate)
from fastapi import Request, Header

router = APIRouter()

_ADMIN_SENTINEL = "__admin__"


def _db_phone(empresa_id: str, contact_id: str) -> str:
    """Para contactos migrados a slug, resuelve el phone real para queries a DB.
    Lee name.txt del slug dir. Si no existe, devuelve contact_id tal cual.
    """
    return get_contact_display_name(empresa_id, contact_id) or contact_id


def _require_empresa_or_admin(request: Request, x_password: str = Header(default=None)) -> str:
    if x_password == ADMIN_PASSWORD:
        return _ADMIN_SENTINEL
    empresa_id = get_empresa_id_from_token(request)
    if not empresa_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return empresa_id


def _check_auth(empresa_id: str, token_bot_id: str = Depends(_require_empresa_or_admin)) -> str:
    if token_bot_id != _ADMIN_SENTINEL and token_bot_id != empresa_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
    return token_bot_id


@router.get("/summarizer/{empresa_id}")
async def list_summaries(empresa_id: str, _: str = Depends(_check_auth)):
    """Lista los contactos que tienen resumen acumulado, con nombre si está en la agenda."""
    phones = summarizer.list_contacts(empresa_id)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(
                "SELECT cc.value, c.name FROM contact_channels cc "
                "JOIN contacts c ON cc.contact_id = c.id "
                "WHERE c.connection_id = :eid AND cc.type = 'whatsapp'"
            ),
            {"eid": empresa_id},
        )).fetchall()
    phone_to_name = {r[0]: r[1] for r in rows}
    from graphs.nodes.summarize import _BASE
    contacts = []
    for p in phones:
        # Prioridad: DB por phone > name.txt (nombre original pre-slug) > slug mismo
        name = phone_to_name.get(p) or get_contact_display_name(empresa_id, p) or p
        contacts.append({"phone": p, "name": name})
    return {
        "contacts": contacts,
        "path": str(_BASE / empresa_id),
    }


@router.get("/summarizer/{empresa_id}/{contact_phone}", response_class=PlainTextResponse)
async def get_summary(empresa_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """Devuelve el resumen acumulado de un contacto como texto plano (Markdown)."""
    content = summarizer.get_summary(empresa_id, contact_phone)
    if content is None:
        raise HTTPException(status_code=404, detail="Sin resumen para este contacto")
    return content


# ─── Helpers de parseo ──────────────────────────────────────────────────────

def _parse_messages(md_content: str, empresa_id: str, contact_phone: str, owner_names: set[str] | None = None) -> list[dict]:
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
                "download_url": f"/api/summarizer/{empresa_id}/{contact_phone}/docs/{filename}",
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
    for m in messages:
        m.pop("_id", None)
    return messages


# ─── Endpoints de mensajes y adjuntos ───────────────────────────────────────

@router.get("/summarizer/{empresa_id}/{contact_phone}/messages")
async def get_messages(empresa_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """Devuelve los mensajes del resumen (inbound) + respuestas del bot (outbound), ordenados por timestamp."""
    content = summarizer.get_summary(empresa_id, contact_phone)
    if content is None:
        raise HTTPException(status_code=404, detail="Sin resumen para este contacto")

    from config import load_config as _load_config
    _cfg = _load_config()
    _empresa_cfg = next((e for e in _cfg.get("empresas", []) if e["id"] == empresa_id), None)
    owner_names: set[str] = {"Tú"}  # "Tú" siempre es el dueño del teléfono (sync path)
    if _empresa_cfg:
        for ph in _empresa_cfg.get("phones", []):
            if ph.get("owner_name"):
                owner_names.add(ph["owner_name"])

    inbound = _parse_messages(content, empresa_id, contact_phone, owner_names)

    # Cuerpos ya presentes en el .md (texto o transcripción de audio).
    # Sirve para descartar mensajes de DB que sean duplicados del scrape.
    _inbound_bodies: set[str] = set()
    for _m in inbound:
        if _m.get("content"):
            _inbound_bodies.add(_m["content"].strip())
        if _m.get("transcription"):
            _inbound_bodies.add(_m["transcription"].strip())

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(
                "SELECT body, timestamp FROM messages "
                "WHERE connection_id = :eid AND outbound = 1 AND phone = :phone "
                "ORDER BY timestamp ASC"
            ),
            {"eid": empresa_id, "phone": _db_phone(empresa_id, contact_phone)},
        )).fetchall()

    outbound = []
    for body, ts_raw in rows:
        if not _is_useful(body):
            continue
        # Descartar si ya aparece en el .md (scrapeado via delta_sync)
        if body.strip() in _inbound_bodies:
            continue
        ts_iso = None
        if ts_raw:
            try:
                ts_iso = datetime.fromisoformat(str(ts_raw)).isoformat()
            except (ValueError, TypeError):
                pass  # timestamp inválido → ts_iso queda None → se ordena al final
        outbound.append({
            "type": "text",
            "direction": "out",
            "timestamp": ts_iso,
            "content": body.strip(),
        })

    all_msgs = sorted(inbound + outbound, key=lambda m: m.get("timestamp") or "")
    return {"messages": all_msgs}


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


@router.post("/summarizer/{empresa_id}/{contact_phone}/sync")
async def sync_contact(empresa_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """
    FUENTE: DB (no WA Web).
    Reconstruye el .md de un contacto a partir de los mensajes ya guardados en base de datos.
    Solo incluye mensajes entrantes (outbound=0). Para scrape desde WA Web usar /full-resync.
    """
    summarizer.clear_contact(empresa_id, contact_phone)

    phone_for_db = _db_phone(empresa_id, contact_phone)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(
                "SELECT body, timestamp FROM messages "
                "WHERE connection_id = :eid AND outbound = 0 AND phone = :phone "
                "ORDER BY timestamp ASC"
            ),
            {"eid": empresa_id, "phone": phone_for_db},
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
            empresa_id=empresa_id,
            contact_phone=contact_phone,
            contact_name=phone_for_db,
            msg_type="text",
            content=f"{phone_for_db}: {body.strip()}",
            timestamp=ts,
        )
        synced += 1

    return {"synced": synced}


@router.post("/summarizer/{empresa_id}/{contact_phone}/full-resync")
async def full_resync_contact(
    empresa_id: str,
    contact_phone: str,
    from_date: str = Query(default=None),
    max_retries: int = Query(default=1, ge=1, le=10),
    _: str = Depends(_check_auth),
):
    """
    Full re-sync: backup, limpia .md + adjuntos + DB del contacto, luego dispara
    un scrape WA Web completo. Delega en _run_contact_import(force_clear=True).
    """
    from state import wa_session, clients
    from graphs.nodes.summarize import get_contact_display_name as _get_display_name
    from db import get_contacts
    from api.flows import _run_contact_import
    from config import load_config as _load_config
    from datetime import datetime as _dt

    # Resolver nombre del contacto
    contact_name = _get_display_name(empresa_id, contact_phone) or contact_phone
    for contact in await get_contacts(empresa_id):
        wa_chs = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]
        if any(ch["value"] == contact_phone for ch in wa_chs):
            contact_name = contact["name"]
            break

    # Sesión WA activa
    session_id = None
    for bot_phone, client in clients.items():
        if client.get("status") == "ready" and client.get("type") == "whatsapp":
            session_id = bot_phone
            break
    if not session_id or not wa_session:
        raise HTTPException(status_code=503, detail="Sin sesión WA activa")

    # Owner name
    _cfg = _load_config()
    _empresa_cfg = next((e for e in _cfg.get("empresas", []) if e["id"] == empresa_id), None)
    owner_name = None
    if _empresa_cfg:
        for ph in _empresa_cfg.get("phones", []):
            if ph.get("number") == session_id and ph.get("owner_name"):
                owner_name = ph["owner_name"]
                break

    since_date = None
    if from_date:
        try:
            since_date = _dt.fromisoformat(from_date)
        except ValueError:
            pass

    result = await _run_contact_import(
        empresa_id=empresa_id,
        contact_name=contact_name,
        contact_phone=contact_phone,
        session_id=session_id,
        wa_session=wa_session,
        owner_name=owner_name,
        since_date=since_date,
        max_retries=max_retries,
        force_clear=True,
    )

    return {"scraped": result["scraped"], "saved": result["new"], "contact_name": contact_name}


@router.post("/summarizer/{empresa_id}/migrate-to-slugs")
async def migrate_to_slugs(empresa_id: str, _: str = Depends(_check_auth)):
    """Migra la estructura vieja ({nombre}.md) a la nueva ({slug}/chat.md). Idempotente."""
    result = migrate_empresa_to_slugs(empresa_id)
    return result


@router.post("/summarizer/{empresa_id}/sync-all")
async def sync_all_contacts(
    empresa_id: str,
    from_date: str = Query(default=None),
    _: str = Depends(_check_auth),
):
    """
    FUENTE: DB (no WA Web).
    Reconstruye el .md de TODOS los contactos de una empresa a partir de la base de datos.
    Solo incluye mensajes entrantes (outbound=0). Para scrape desde WA Web usar /full-resync.

    Si from_date (YYYY-MM-DD): trim del .md desde esa fecha + re-procesa solo esos mensajes.
    Sin from_date: rebuild completo desde cero.
    """
    cutoff_dt = None
    if from_date:
        try:
            cutoff_dt = datetime.fromisoformat(from_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="from_date inválido, usar YYYY-MM-DD")

    results = []

    async with AsyncSessionLocal() as session:
        # Fuente de verdad: todos los phones con mensajes en DB para esta empresa.
        # Incluye contactos nuevos que nunca tuvieron .md (bootstrap desde cero).
        if cutoff_dt:
            phone_rows = (await session.execute(
                text("SELECT DISTINCT phone FROM messages WHERE connection_id = :eid AND outbound = 0 AND timestamp >= :cutoff"),
                {"eid": empresa_id, "cutoff": from_date},
            )).fetchall()
        else:
            phone_rows = (await session.execute(
                text("SELECT DISTINCT phone FROM messages WHERE connection_id = :eid AND outbound = 0"),
                {"eid": empresa_id},
            )).fetchall()

        phones = [r[0] for r in phone_rows if r[0]]

        for phone in phones:
            # Saltar contactos que pertenecen principalmente a otra empresa
            # (evita que grupos/contactos de empresas que comparten número contaminen
            # el sumarizador de esta empresa).
            own_count = (await session.execute(
                text("SELECT COUNT(*) FROM messages WHERE connection_id = :eid AND phone = :phone AND outbound = 0"),
                {"eid": empresa_id, "phone": phone},
            )).scalar() or 0
            other_count = (await session.execute(
                text("SELECT COUNT(*) FROM messages WHERE connection_id != :eid AND phone = :phone AND outbound = 0"),
                {"eid": empresa_id, "phone": phone},
            )).scalar() or 0
            if other_count > own_count * 3:
                results.append({"phone": phone, "synced": 0, "skipped": True, "reason": "primarily_other_empresa"})
                continue

            if cutoff_dt:
                trim_contact_from_date(empresa_id, phone, cutoff_dt)
                rows = (await session.execute(
                    text(
                        "SELECT body, timestamp FROM messages "
                        "WHERE connection_id = :eid AND outbound = 0 AND phone = :phone "
                        "AND timestamp >= :cutoff ORDER BY timestamp ASC"
                    ),
                    {"eid": empresa_id, "phone": phone, "cutoff": from_date},
                )).fetchall()
            else:
                summarizer.clear_contact(empresa_id, phone)
                rows = (await session.execute(
                    text(
                        "SELECT body, timestamp FROM messages "
                        "WHERE connection_id = :eid AND outbound = 0 AND phone = :phone "
                        "ORDER BY timestamp ASC"
                    ),
                    {"eid": empresa_id, "phone": phone},
                )).fetchall()

            contact_display = _db_phone(empresa_id, phone)
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
                    empresa_id=empresa_id,
                    contact_phone=phone,
                    contact_name=contact_display,
                    msg_type="text",
                    content=f"{contact_display}: {body.strip()}",
                    timestamp=ts,
                )
                synced += 1
            results.append({"phone": phone, "synced": synced})

    return {"contacts": len(phones), "details": results}


@router.get("/summarizer/{empresa_id}/{contact_phone}/docs/{filename}")
async def download_attachment(
    empresa_id: str, contact_phone: str, filename: str,
    _: str = Depends(_check_auth),
):
    """Descarga un adjunto del contacto."""
    from graphs.nodes.summarize import get_attachments_dir
    attachments_dir = get_attachments_dir(empresa_id, contact_phone)
    file_path = attachments_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/summarizer/{empresa_id}/backup-and-clean")
async def backup_and_clean(empresa_id: str, _: str = Depends(_check_auth)):
    """
    Hace backup de todos los chat.md de la empresa (→ chat.bak.md) y los borra.
    El summarize sigue acumulando desde cero a partir del próximo mensaje.
    """
    import shutil as _shutil
    from graphs.nodes.summarize import _BASE, slugify
    empresa_dir = _BASE / empresa_id
    backed_up = 0
    if empresa_dir.exists():
        for md_file in empresa_dir.rglob("chat.md"):
            bak = md_file.with_name("chat.bak.md")
            _shutil.copy2(md_file, bak)
            md_file.unlink()
            backed_up += 1
    # Invalidar dedup en memoria
    from graphs.nodes.summarize import _dedup, _dedup_loaded
    keys = [k for k in list(_dedup_loaded) if k[0] == empresa_id]
    for k in keys:
        _dedup_loaded.discard(k)
        _dedup.pop(k, None)
    return {"backed_up": backed_up, "path": str(empresa_dir)}


@router.get("/summarizer/{empresa_id}/download")
async def download_summaries(empresa_id: str, _: str = Depends(_check_auth)):
    """Descarga todos los resúmenes de la empresa como un archivo ZIP."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    from graphs.nodes.summarize import _BASE
    empresa_dir = _BASE / empresa_id
    if not empresa_dir.exists():
        raise HTTPException(status_code=404, detail="No hay resúmenes para esta empresa")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for md_file in empresa_dir.rglob("*.md"):
            zf.write(md_file, md_file.relative_to(empresa_dir))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="summaries_{empresa_id}.zip"'},
    )


@router.get("/summarizer/{empresa_id}/{contact_phone}/count-dom")
async def count_dom_messages(
    empresa_id: str,
    contact_phone: str,
    since_date: str | None = Query(default=None, description="YYYY-MM-DD — cuenta solo hasta esta fecha"),
    _: str = Depends(_check_auth),
):
    """
    Cuenta mensajes en el DOM de WA Web para un contacto scrolleando todo el historial.
    Usa el mismo mecanismo que full-resync pero sin extraer contenido — solo cuenta.
    Útil para validar manualmente cuántos mensajes tiene WA vs cuántos capturó el scraper.

    Retorna: total, from_date, to_date, contact_name
    """
    from state import wa_session, clients
    from db import get_contacts as _get_contacts
    from graphs.nodes.summarize import get_contact_display_name as _get_display_name

    contact_name = _get_display_name(empresa_id, contact_phone) or contact_phone
    for contact in await _get_contacts(empresa_id):
        wa_chs = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]
        if any(ch["value"] == contact_phone for ch in wa_chs):
            contact_name = contact["name"]
            break

    session_id = None
    for bot_phone, client in clients.items():
        if client.get("status") == "ready" and client.get("type") == "whatsapp":
            session_id = bot_phone
            break
    if not session_id or not wa_session:
        raise HTTPException(status_code=503, detail="Sin sesión WA activa")

    stop_ts = None
    if since_date:
        try:
            from datetime import datetime as _dt
            stop_ts = _dt.strptime(since_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="since_date inválido, usar YYYY-MM-DD")

    msgs = await wa_session.scrape_full_history_v2(
        session_id,
        contact_name,
        count_only=True,
        stop_before_ts=stop_ts,
    )

    timestamps = sorted(m["timestamp"] for m in msgs if m.get("timestamp"))
    return {
        "total": len(timestamps),
        "from_date": timestamps[0] if timestamps else None,
        "to_date": timestamps[-1] if timestamps else None,
        "contact_name": contact_name,
    }
