"""
API para consultar los resúmenes acumulados por la herramienta sumarizadora.
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import text

from db import AsyncSessionLocal
from middleware_auth import get_empresa_bot_id
from api.deps import ADMIN_PASSWORD
from tools import summarizer
from fastapi import Request, Header

router = APIRouter()

_ADMIN_SENTINEL = "__admin__"


def _require_empresa_or_admin(request: Request, x_password: str = Header(default=None)) -> str:
    if x_password == ADMIN_PASSWORD:
        return _ADMIN_SENTINEL
    bot_id = get_empresa_bot_id(request)
    if not bot_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return bot_id


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


class SyncBody(BaseModel):
    contact_phone: str | None = None


@router.post("/summarizer/{empresa_id}/sync")
async def sync_history(empresa_id: str, body: SyncBody = SyncBody(), _: str = Depends(_check_auth)):
    """Backfill: lee mensajes de la DB y los acumula en los archivos .md.
    Si contact_phone está presente, solo sincroniza ese contacto.
    Borra los archivos existentes antes de escribir para evitar duplicados."""
    if body.contact_phone:
        summarizer.clear_contact(empresa_id, body.contact_phone)
    else:
        summarizer.clear_empresa(empresa_id)

    extra_filter = "AND m.phone = :phone " if body.contact_phone else ""
    params: dict = {"eid": empresa_id}
    if body.contact_phone:
        params["phone"] = body.contact_phone

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(
                "SELECT m.phone, m.name, m.body, m.timestamp "
                "FROM messages m "
                "JOIN contacts c ON c.bot_id = :eid "
                "JOIN contact_channels cc ON cc.contact_id = c.id AND cc.value = m.phone "
                f"WHERE m.bot_id = :eid AND m.outbound = 0 {extra_filter}"
                "ORDER BY m.timestamp ASC"
            ),
            params,
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
