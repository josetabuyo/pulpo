"""
Router: /connections

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Note: the original source had bot-or-admin auth on filter-config endpoints
and google-connection endpoints. In this layer all endpoints are auth-free;
access control is handled by the parent mount.
"""
import json
import logging
import uuid

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


# ─── Google connections (bot-scoped, under /bots/{bot_id}/google-connections) ─
# These are defined here alongside the rest of connections logic even though
# their path prefix differs — the parent app mounts them without a prefix so
# we use full sub-paths.

class GoogleConnectionCreate(BaseModel):
    credentials_json: str
    label: str | None = None


@router.get("/bots/{bot_id}/google-connections")
async def list_google_connections(bot_id: str):
    try:
        return await connections_svc.list_google_connections(bot_id=bot_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bots/{bot_id}/google-connections", status_code=201)
async def create_google_connection(bot_id: str, body: GoogleConnectionCreate):
    try:
        info = json.loads(body.credentials_json)
    except Exception:
        raise HTTPException(status_code=400, detail="credentials_json no es JSON válido")
    email = info.get("client_email", "")
    if not email or "private_key" not in info:
        raise HTTPException(status_code=400, detail="El JSON debe tener client_email y private_key")
    conn_id = str(uuid.uuid4())
    label = body.label or email.split("@")[0]
    try:
        return await connections_svc.create_google_connection(
            conn_id=conn_id,
            bot_id=bot_id,
            credentials_json=body.credentials_json,
            email=email,
            label=label,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/bots/{bot_id}/google-connections/{conn_id}")
async def delete_google_connection(bot_id: str, conn_id: str):
    if conn_id == "pulpo-default":
        raise HTTPException(status_code=403, detail="La conexión Pulpo no se puede eliminar")
    try:
        return await connections_svc.delete_google_connection(
            bot_id=bot_id,
            conn_id=conn_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
