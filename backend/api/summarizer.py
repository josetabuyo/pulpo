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

def _parse_messages(md_content: str, empresa_id: str, contact_phone: str) -> list[dict]:
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

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        timestamp_str = None
        msg_line = None
        reply_to = None

        for line in block.split("\n"):
            if line.startswith("## "):
                timestamp_str = line[3:].strip()
            elif line.startswith("**["):
                msg_line = line
            elif line.startswith("> ↩"):
                # Línea de cita/respuesta: "> ↩ texto citado"
                reply_to = line[3:].strip()  # Quita "> ↩" y espacios

        if not msg_line:
            continue

        m = re.match(r'\*\*\[([^\]]+)\]\*\*\s*(.*)', msg_line, re.DOTALL)
        if not m:
            continue

        type_info = m.group(1).strip()
        content = m.group(2).strip()

        ts_iso = None
        if timestamp_str:
            try:
                ts_iso = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M").isoformat()
            except ValueError:
                ts_iso = timestamp_str

        if type_info in ("image", "imagen"):
            # Mensajes de imagen — mostrar como burbuja especial
            # content puede ser "[imagen: nombre.jpg]" o solo el nombre
            img_match = re.match(r'\[imagen(?:\s*guardada)?:\s*([^\]]+)\]', content)
            img_name = img_match.group(1).strip() if img_match else content
            # Extraer sender si hay "Nombre: " prefix
            img_sender = None
            gs = re.match(r'^([^\[:]{2,40}):\s+(.*)', content, re.DOTALL)
            if gs:
                img_sender = gs.group(1).strip()
                img_name = gs.group(2).strip()
                img_m2 = re.match(r'\[imagen(?:\s*guardada)?:\s*([^\]]+)\]', img_name)
                if img_m2:
                    img_name = img_m2.group(1).strip()
            messages.append({
                "type": "image",
                "direction": "in",
                "timestamp": ts_iso,
                "sender": img_sender,
                "filename": img_name,
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
                "direction": "in",
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
            messages.append({
                "type": "document",
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
                "direction": "in",
                "timestamp": ts_iso,
                "sender": sender,
                "content": text_content,
                "reply_to": reply_to,
            })

    return messages


# ─── Endpoints de mensajes y adjuntos ───────────────────────────────────────

@router.get("/summarizer/{empresa_id}/{contact_phone}/messages")
async def get_messages(empresa_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """Devuelve los mensajes del resumen (inbound) + respuestas del bot (outbound), ordenados por timestamp."""
    content = summarizer.get_summary(empresa_id, contact_phone)
    if content is None:
        raise HTTPException(status_code=404, detail="Sin resumen para este contacto")

    inbound = _parse_messages(content, empresa_id, contact_phone)

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
_SKIP_CONTAINS = ["[audio", "audio — sin blob", "audio — no disponible", "audio — error"]
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
    """Re-sincroniza el resumen de UN contacto desde la DB, filtrando ruido (audios sin transcripción, etc.)."""
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
            content=body.strip(),
            timestamp=ts,
        )
        synced += 1

    return {"synced": synced}


@router.post("/summarizer/{empresa_id}/{contact_phone}/full-resync")
async def full_resync_contact(empresa_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """
    Full re-sync: borra el .md, adjuntos y .bak del contacto, luego dispara un
    scrape WA Web completo (scrape_full_history_v2, sin stop_before_ts).
    """
    from backend_state import wa_session, clients
    from api.whatsapp import log_message_historic
    from graphs.nodes.summarize import accumulate as _accumulate, get_attachments_dir as _get_att_dir
    from graphs.nodes.state import FlowState as _FlowState

    # 1. Limpiar todo
    clear_contact_full(empresa_id, contact_phone)

    # 2. Buscar sesión WA activa para esta empresa
    session_id = None
    for bot_phone, client in clients.items():
        if client.get("empresa_id") == empresa_id:
            session_id = bot_phone
            break
    if not session_id or not wa_session:
        raise HTTPException(status_code=503, detail="Sin sesión WA activa para esta empresa")

    # 3. Buscar nombre del contacto en la configuración
    from api.whatsapp import get_contacts
    contact_name = contact_phone
    for contact in await get_contacts(empresa_id):
        wa_chs = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]
        if any(ch["value"] == contact_phone for ch in wa_chs):
            contact_name = contact["name"]
            break

    # 4. Scrape completo v2
    doc_dir = _get_att_dir(empresa_id, contact_phone)
    messages = await wa_session.scrape_full_history_v2(
        session_id, contact_name, doc_save_dir=doc_dir
    )
    messages.sort(key=lambda m: m.get("timestamp") or "")

    # 5. Acumular en el .md
    saved = 0
    from datetime import datetime as _dt
    for msg in messages:
        body = msg.get("body", "")
        sender = msg.get("sender")
        if sender:
            body = f"{sender}: {body}"
        if not body.strip():
            continue
        ts = None
        try:
            ts = _dt.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        msg_type = msg.get("msg_type", "text")
        _accumulate(
            empresa_id=empresa_id,
            contact_phone=contact_phone,
            contact_name=contact_name,
            msg_type=msg_type,
            content=body.strip(),
            timestamp=ts,
        )
        saved += 1

    return {"scraped": len(messages), "saved": saved, "contact_name": contact_name}


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
    Reconstruye el .md de TODOS los contactos de una empresa desde la DB.
    Si from_date (YYYY-MM-DD) está presente, solo re-procesa mensajes desde esa fecha
    (trim del .md a partir de esa fecha + acumular desde DB).
    Sin from_date: rebuild completo desde DB.
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
                    contact_name=phone,
                    msg_type="text",
                    content=body.strip(),
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
