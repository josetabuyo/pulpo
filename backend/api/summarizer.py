"""
API para consultar los resúmenes acumulados por la herramienta sumarizadora.
"""
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse, FileResponse
from middleware_auth import get_empresa_id_from_token
from api.deps import ADMIN_PASSWORD
from graphs.nodes.summarize import (
    get_summary, list_contacts, clear_empresa, clear_contact, accumulate
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
    """Lista los contactos que tienen resumen acumulado."""
    return {"contacts": summarizer.list_contacts(empresa_id)}


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

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        timestamp_str = None
        msg_line = None

        for line in block.split("\n"):
            if line.startswith("## "):
                timestamp_str = line[3:].strip()
            elif line.startswith("**["):
                msg_line = line

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

        if type_info.startswith("audio"):
            duration = type_info[5:].strip()
            t_match = re.match(r'_transcripción:_\s*(.*)', content, re.DOTALL)
            transcription = t_match.group(1).strip() if t_match else content
            messages.append({
                "type": "audio",
                "direction": "in",
                "timestamp": ts_iso,
                "duration": duration,
                "transcription": transcription,
            })
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
            })
        else:
            messages.append({
                "type": "text",
                "direction": "in",
                "timestamp": ts_iso,
                "content": content,
            })

    return messages


# ─── Endpoints de mensajes y adjuntos ───────────────────────────────────────

@router.get("/summarizer/{empresa_id}/{contact_phone}/messages")
async def get_messages(empresa_id: str, contact_phone: str, _: str = Depends(_check_auth)):
    """Devuelve los mensajes del resumen como lista JSON estructurada."""
    content = summarizer.get_summary(empresa_id, contact_phone)
    if content is None:
        raise HTTPException(status_code=404, detail="Sin resumen para este contacto")
    return {"messages": _parse_messages(content, empresa_id, contact_phone)}


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
