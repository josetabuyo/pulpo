"""
API para consultar los resúmenes acumulados por la herramienta sumarizadora.
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from db import AsyncSessionLocal
from middleware_auth import require_empresa_auth
from tools import summarizer

router = APIRouter()


def _check_auth(empresa_id: str, token_bot_id: str = Depends(require_empresa_auth)) -> str:
    if token_bot_id != empresa_id:
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


@router.post("/summarizer/{empresa_id}/sync")
async def sync_history(empresa_id: str, _: str = Depends(_check_auth)):
    """Backfill: lee todos los mensajes entrantes de la DB y los acumula en los archivos .md.
    Borra los archivos existentes antes de escribir para evitar duplicados."""
    # Limpiar archivos actuales de esta empresa
    summarizer.clear_empresa(empresa_id)

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(
                "SELECT m.phone, m.name, m.body, m.timestamp "
                "FROM messages m "
                "JOIN contacts c ON c.bot_id = :eid "
                "JOIN contact_channels cc ON cc.contact_id = c.id AND cc.value = m.phone "
                "WHERE m.bot_id = :eid AND m.outbound = 0 "
                "ORDER BY m.timestamp ASC"
            ),
            {"eid": empresa_id},
        )).fetchall()

    for phone, name, body, ts_raw in rows:
        try:
            ts = datetime.fromisoformat(str(ts_raw)) if ts_raw else None
        except ValueError:
            ts = None
        summarizer.accumulate(
            empresa_id=empresa_id,
            contact_phone=phone,
            contact_name=name or phone,
            msg_type="text",
            content=body,
            timestamp=ts,
        )

    return {"synced": len(rows)}
