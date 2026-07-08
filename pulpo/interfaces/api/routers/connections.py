"""
Router: /connections

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Note: the original source had bot-or-admin auth on filter-config endpoints
and google-connection endpoints. In this layer all endpoints are auth-free;
access control is handled by the parent mount.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pulpo.business import connections as connections_svc

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Phone connections ────────────────────────────────────────────────────────

@router.get("")
def get_connections():
    try:
        return connections_svc.list_connections()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class PhoneCreate(BaseModel):
    botId: str
    botName: str | None = None
    number: str


@router.post("", status_code=201)
def create_connection(body: PhoneCreate):
    if not body.botId or not body.number:
        raise HTTPException(status_code=400, detail="botId y number son requeridos")
    try:
        return connections_svc.create_connection(
            bot_id=body.botId,
            bot_name=body.botName,
            number=body.number,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{number}")
def delete_connection(number: str):
    try:
        found = connections_svc.delete_connection(number=number)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not found:
        raise HTTPException(status_code=404, detail=f"Número no encontrado: {number}")
    return found


class ConnectionSettingsPatch(BaseModel):
    allow_mass: bool


@router.patch("/{number}/settings")
def patch_connection_settings(number: str, body: ConnectionSettingsPatch):
    try:
        return connections_svc.patch_connection_settings(
            number=number,
            allow_mass=body.allow_mass,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


class MovePhone(BaseModel):
    targetBotId: str


@router.post("/{number}/move")
def move_connection(number: str, body: MovePhone):
    if not body.targetBotId:
        raise HTTPException(status_code=400, detail="targetBotId requerido")
    try:
        return connections_svc.move_connection(
            number=number,
            target_bot_id=body.targetBotId,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Filter config ────────────────────────────────────────────────────────────

class DefaultFilterBody(BaseModel):
    include_all_known: bool = False
    include_unknown: bool = False
    included: list[str] = []
    excluded: list[str] = []


@router.put("/{number}/filter-config")
def put_connection_filter(number: str, body: DefaultFilterBody):
    filter_dict = body.model_dump()
    try:
        ok = connections_svc.set_connection_filter(number=number, filter_dict=filter_dict)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return {"ok": True, "filter": filter_dict}


@router.get("/{number}/filter-config")
def get_connection_filter(number: str):
    try:
        df = connections_svc.get_connection_filter(number=number)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if df is None:
        return {"include_all_known": False, "include_unknown": False, "included": [], "excluded": []}
    return df


@router.delete("/{number}/filter-config")
def delete_connection_filter(number: str):
    try:
        ok = connections_svc.set_connection_filter(number=number, filter_dict=None)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return {"ok": True}


