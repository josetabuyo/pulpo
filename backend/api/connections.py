import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request, Header
from pydantic import BaseModel

from api.deps import require_admin, ADMIN_PASSWORD
from config import load_config, save_config, get_connection_default_filter, set_connection_default_filter
from middleware_auth import get_bot_id_from_token
from state import clients
import db

logger = logging.getLogger(__name__)

_ADMIN_SENTINEL = "__admin__"

def _require_bot_or_admin(request: Request, x_password: str = Header(default=None)) -> str:
    if x_password == ADMIN_PASSWORD:
        return _ADMIN_SENTINEL
    bot_id = get_bot_id_from_token(request)
    if not bot_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return bot_id

def _check_number_access(number: str, token_bot_id: str):
    """Verifica que el número pertenezca a la bot autenticada (o es admin)."""
    if token_bot_id == _ADMIN_SENTINEL:
        return
    config = load_config()
    for bot in config.get("bots", []):
        if bot["id"] == token_bot_id:
            phones = [p["number"] for p in bot.get("phones", [])]
            if number in phones:
                return
            raise HTTPException(403, "No autorizado para este número")
    raise HTTPException(403, "Bot no encontrada")

router = APIRouter()


@router.get("/connections", dependencies=[Depends(require_admin)])
def get_connections():
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        for phone in bot.get("phones", []):
            session_id = phone["number"]
            result.append({
                "botId": bot["id"],
                "botName": bot["name"],
                "number": phone["number"],
                "sessionId": session_id,
                "status": clients.get(session_id, {}).get("status", "stopped"),
            })
    return result


class PhoneCreate(BaseModel):
    botId: str
    botName: str | None = None
    number: str


@router.post("/connections", dependencies=[Depends(require_admin)], status_code=201)
def create_connection(body: PhoneCreate):
    if not body.botId or not body.number:
        raise HTTPException(status_code=400, detail="botId y number son requeridos")

    config = load_config()
    bot = next((e for e in config.get("bots", []) if e["id"] == body.botId), None)

    if not bot:
        if not body.botName:
            raise HTTPException(status_code=400, detail="Bot nueva requiere botName")
        bot = {"id": body.botId, "name": body.botName, "phones": []}
        config.setdefault("bots", []).append(bot)

    # Permitir que el mismo número esté en varias bots (conexión compartida con filtros distintos)
    if any(p["number"] == body.number for p in bot.get("phones", [])):
        raise HTTPException(status_code=409, detail=f'El número ya está en esta bot.')

    bot.setdefault("phones", []).append({"number": body.number})

    save_config(config)
    return {"ok": True, "sessionId": body.number}



@router.delete("/connections/{number}", dependencies=[Depends(require_admin)])
def delete_connection(number: str):
    config = load_config()
    for bot in config.get("bots", []):
        idx = next((i for i, p in enumerate(bot.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            session_id = number
            if session_id in clients:
                try:
                    clients[session_id]["client"].destroy()
                except Exception as e:
                    logger.warning("[connections] destroy de %s falló: %s", session_id, e)
                del clients[session_id]
            bot["phones"].pop(idx)
            config["bots"] = [e for e in config["bots"] if e.get("phones")]
            save_config(config)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Número no encontrado")


class ConnectionSettingsPatch(BaseModel):
    allow_mass: bool


@router.patch("/connections/{number}/settings", dependencies=[Depends(require_admin)])
def patch_connection_settings(number: str, body: ConnectionSettingsPatch):
    config = load_config()
    for bot in config.get("bots", []):
        for phone in bot.get("phones", []):
            if phone.get("number") == number:
                phone["allow_mass"] = body.allow_mass
                save_config(config)
                return {"ok": True, "allow_mass": body.allow_mass}
    raise HTTPException(status_code=404, detail="Número no encontrado")


class MovePhone(BaseModel):
    targetBotId: str


@router.post("/connections/{number}/move", dependencies=[Depends(require_admin)])
def move_connection(number: str, body: MovePhone):
    if not body.targetBotId:
        raise HTTPException(status_code=400, detail="targetBotId requerido")

    config = load_config()
    target_bot = next((e for e in config.get("bots", []) if e["id"] == body.targetBotId), None)
    if not target_bot:
        raise HTTPException(status_code=404, detail="Bot destino no encontrada")

    source_bot = None
    phone_entry = None
    for e in config.get("bots", []):
        idx = next((i for i, p in enumerate(e.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            source_bot = e
            phone_entry = e["phones"].pop(idx)
            break

    if not source_bot:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    if source_bot["id"] == body.targetBotId:
        raise HTTPException(status_code=400, detail="El teléfono ya está en esa bot")

    target_bot.setdefault("phones", []).append(phone_entry)
    save_config(config)
    return {"ok": True, "from": source_bot["id"], "to": body.targetBotId}


# ─── Filtro default por conexión ─────────────────────────────────────────────

class DefaultFilterBody(BaseModel):
    include_all_known: bool = False
    include_unknown: bool = False
    included: list[str] = []
    excluded: list[str] = []


@router.put("/connections/{number}/filter-config")
def put_connection_filter(number: str, body: DefaultFilterBody, token: str = Depends(_require_bot_or_admin)):
    """Guarda el filtro default de una conexión (bot-aware para conexiones compartidas)."""
    _check_number_access(number, token)
    filter_dict = body.model_dump()
    bot_id = None if token == _ADMIN_SENTINEL else token
    ok = set_connection_default_filter(number, filter_dict, bot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return {"ok": True, "filter": filter_dict}


@router.get("/connections/{number}/filter-config")
def get_connection_filter(number: str, token: str = Depends(_require_bot_or_admin)):
    """Retorna el filtro default de una conexión (o vacío si no tiene)."""
    _check_number_access(number, token)
    bot_id = None if token == _ADMIN_SENTINEL else token
    df = get_connection_default_filter(number, bot_id)
    if df is None:
        return {"include_all_known": False, "include_unknown": False, "included": [], "excluded": []}
    return df


@router.delete("/connections/{number}/filter-config", dependencies=[Depends(require_admin)])
def delete_connection_filter(number: str):
    """Elimina el filtro default de una conexión (solo admin)."""
    ok = set_connection_default_filter(number, None)
    if not ok:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return {"ok": True}


# ─── Google Connections ───────────────────────────────────────────────────────

class GoogleConnectionCreate(BaseModel):
    credentials_json: str
    label: str | None = None


def _check_bot_auth(bot_id: str, request: Request, x_password: str | None) -> str:
    """Permite admin o la propia bot. Retorna bot_id o _ADMIN_SENTINEL."""
    if x_password == ADMIN_PASSWORD:
        return _ADMIN_SENTINEL
    token_bot_id = get_bot_id_from_token(request)
    if not token_bot_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    if token_bot_id != bot_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta bot")
    return token_bot_id


@router.get("/bots/{bot_id}/google-connections")
async def list_google_connections(
    bot_id: str,
    request: Request,
    x_password: str = Header(default=None),
):
    _check_bot_auth(bot_id, request, x_password)
    conns = await db.get_google_connections(bot_id)
    return conns


@router.post("/bots/{bot_id}/google-connections", status_code=201)
async def create_google_connection(
    bot_id: str,
    body: GoogleConnectionCreate,
    request: Request,
    x_password: str = Header(default=None),
):
    _check_bot_auth(bot_id, request, x_password)
    try:
        info = json.loads(body.credentials_json)
    except Exception:
        raise HTTPException(status_code=400, detail="credentials_json no es JSON válido")
    email = info.get("client_email", "")
    if not email or "private_key" not in info:
        raise HTTPException(status_code=400, detail="El JSON debe tener client_email y private_key")
    conn_id = str(uuid.uuid4())
    label = body.label or email.split("@")[0]
    await db.create_google_connection(
        id=conn_id,
        bot_id=bot_id,
        credentials_json=body.credentials_json,
        email=email,
        label=label,
    )
    return {"ok": True, "id": conn_id, "email": email, "label": label}


@router.delete("/bots/{bot_id}/google-connections/{conn_id}")
async def delete_google_connection(
    bot_id: str,
    conn_id: str,
    request: Request,
    x_password: str = Header(default=None),
):
    _check_bot_auth(bot_id, request, x_password)
    if conn_id == "pulpo-default":
        raise HTTPException(status_code=403, detail="La conexión Pulpo no se puede eliminar")
    conns = await db.get_google_connections(bot_id)
    if not any(c["id"] == conn_id for c in conns):
        raise HTTPException(status_code=404, detail="Conexión no encontrada para esta bot")
    ok = await db.delete_google_connection(conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    return {"ok": True}
