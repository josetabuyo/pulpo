"""
API para consultar los resúmenes acumulados por la herramienta sumarizadora.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse

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
