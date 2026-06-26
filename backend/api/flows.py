"""
API REST de flows (grafos de agente).

GET    /api/flow/node-types                      → catálogo de tipos de nodo (público)
GET    /api/bots/{id}/flows                  → lista de flows de la bot (auth)
POST   /api/bots/{id}/flows                  → crear flow (auth)
GET    /api/bots/{id}/flows/{flow_id}        → detalle con definition (auth)
PUT    /api/bots/{id}/flows/{flow_id}        → actualizar (auth)
DELETE /api/bots/{id}/flows/{flow_id}        → eliminar (auth)
"""
import os
import logging
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi import Header
from pydantic import BaseModel
from typing import Optional

_log = logging.getLogger(__name__)

import db
from config import load_config
from middleware_auth import get_bot_id_from_token
from graphs.node_types import NODE_TYPES
from graphs.nodes import NODE_REGISTRY

router = APIRouter()

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _require_bot(bot_id: str, request: Request, x_password: Optional[str]) -> dict:
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrada")
    if x_password and x_password == _ADMIN_PASSWORD:
        return bot
    token_bot_id = get_bot_id_from_token(request)
    if not token_bot_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    if token_bot_id != bot_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta bot")
    return bot


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/flow/node-types")
def list_node_types():
    """
    Catálogo de tipos de nodo: id, label, color, description, schema.
    schema es una lista ordenada de campos: [{key, type, label, default?, hint?, rows?, required?, options?, show_if?}]
    El frontend lo usa para renderizar el panel de configuración sin hardcodear nada.
    """
    result = []
    for nt in NODE_TYPES.values():
        node_class = NODE_REGISTRY.get(nt.id)
        schema_dict = node_class.config_schema() if node_class else {}
        schema = [{"key": k, **v} for k, v in schema_dict.items()]
        # Primer párrafo del docstring de la clase (sin los Config: detallados)
        raw_doc = (node_class.__doc__ or '').strip() if node_class else ''
        help_text = raw_doc.split('\n\nConfig:')[0].strip() if raw_doc else ''
        result.append({
            "id":          nt.id,
            "label":       nt.label,
            "color":       nt.color,
            "description": nt.description,
            "help":        help_text,
            "schema":      schema,
        })
    return result


# ─── Schemas ─────────────────────────────────────────────────────────────────

class FlowIn(BaseModel):
    name: str
    definition: dict | None = None
    connection_id: str | None = None
    contact_phone: str | None = None
    contact_filter: dict | None = None


class FlowUpdate(BaseModel):
    name: str | None = None
    definition: dict | None = None
    connection_id: str | None = None
    contact_phone: str | None = None
    contact_filter: dict | None = None
    active: bool | None = None


# ─── Cuentas Google configuradas ─────────────────────────────────────────────

@router.get("/flow/google-accounts")
def list_google_accounts():
    """
    Devuelve las cuentas de servicio Google configuradas.
    Por ahora soporta una sola cuenta via GOOGLE_SERVICE_ACCOUNT_JSON.
    Retorna [{id, email, label}] para poblar el selector en el frontend.
    """
    import json as _json
    accounts = []
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        try:
            d = _json.loads(sa_json)
            accounts.append({
                "id":    "default",
                "email": d.get("client_email", ""),
                "label": "Cuenta principal",
            })
        except ValueError as e:
            logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON malformado — cuenta default omitida: %s", e)
    return accounts


# ─── Caché de nodos sheet ────────────────────────────────────────────────────

@router.post("/flow/clear-sheet-cache")
def clear_sheet_cache():
    """Limpia el caché en memoria de fetch_sheet, search_sheet y gsheet."""
    from graphs.nodes.fetch_sheet import _sheet_cache
    from graphs.nodes.search_sheet import _rows_cache as _search_cache
    from graphs.nodes.gsheet import _rows_cache as _gsheet_cache
    n = len(_sheet_cache) + len(_search_cache) + len(_gsheet_cache)
    _sheet_cache.clear()
    _search_cache.clear()
    _gsheet_cache.clear()
    return {"ok": True, "cleared": n}


# ─── Endpoints de flows CRUD ──────────────────────────────────────────────────

@router.get("/bots/{bot_id}/flows")
async def list_flows(
    bot_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_bot(bot_id, request, x_password)
    return await db.get_flows(bot_id)


@router.post("/bots/{bot_id}/flows", status_code=201)
async def create_flow(
    bot_id: str,
    body: FlowIn,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_bot(bot_id, request, x_password)
    try:
        flow_id = await db.create_flow(
            bot_id=bot_id,
            name=body.name,
            definition=body.definition,
            connection_id=body.connection_id,
            contact_phone=body.contact_phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await db.get_flow(flow_id)


@router.get("/bots/{bot_id}/flows/{flow_id}")
async def get_flow(
    bot_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_bot(bot_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    return flow


@router.put("/bots/{bot_id}/flows/{flow_id}")
async def update_flow(
    bot_id: str,
    flow_id: str,
    body: FlowUpdate,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_bot(bot_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    updates = body.model_dump(exclude_none=True)

    # Inyectar connection_id y contact_filter en el nodo message_trigger de la definition.
    # El compiler lee estos valores desde el config del nodo, no desde el registro del flow.
    if "definition" in updates:
        definition = updates["definition"]
        new_conn = updates.get("connection_id")
        new_cf   = updates.get("contact_filter")
        for node in definition.get("nodes", []):
            if node.get("type") == "message_trigger":
                cfg = node.setdefault("config", {})
                if new_conn is not None:
                    cfg["connection_id"] = new_conn
                if new_cf is not None:
                    cfg["contact_filter"] = new_cf
                break

    if updates:
        await db.update_flow(flow_id, **updates)
    return await db.get_flow(flow_id)


@router.get("/bots/{bot_id}/flows/has-node/{node_type}")
async def has_node_type(
    bot_id: str,
    node_type: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    """Devuelve {found: bool} indicando si algún flow de la bot contiene el tipo de nodo."""
    _require_bot(bot_id, request, x_password)
    found = await db.bot_has_node_type(bot_id, node_type)
    return {"found": found}


@router.post("/bots/{bot_id}/flows/{flow_id}/replay")
async def replay_flow(
    bot_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
    from_date: Optional[str] = None,
):
    """
    Ejecuta el flow completo para cada mensaje de la DB (from_delta_sync=True,
    los nodos reply/llm no envían nada real).

    from_date (YYYY-MM-DD): si se pasa, solo procesa mensajes desde esa fecha.
    Solo aplica a flows con trigger whatsapp_trigger o telegram_trigger.
    """
    _require_bot(bot_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")

    # Encontrar el nodo trigger y su connection_id
    from graphs.nodes import NODE_REGISTRY, TRIGGER_TYPES
    nodes = flow.get("definition", {}).get("nodes", [])
    trigger = next(
        (n for n in nodes if n.get("type") in TRIGGER_TYPES),
        None,
    )
    if not trigger:
        raise HTTPException(status_code=400, detail="El flow no tiene un nodo trigger de mensajes")

    connection_id = trigger.get("config", {}).get("connection_id", "")
    if not connection_id:
        raise HTTPException(status_code=400, detail="El trigger no tiene connection_id configurado")

    # El canal del replay debe coincidir con el del trigger para que select_trigger aplique
    # (whatsapp_trigger → wavi; telegram_trigger y message_trigger legacy → telegram)
    trigger_cls = NODE_REGISTRY.get(trigger.get("type", ""))
    canal = getattr(trigger_cls, "channel", None) or "telegram"

    date_filter = ""
    date_params: dict = {}
    if from_date:
        date_filter = " AND timestamp >= :from_date"
        date_params["from_date"] = from_date

    from db import AsyncSessionLocal, text as _text
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            _text(
                f"SELECT phone, name, body, timestamp FROM messages "
                f"WHERE connection_id = :cid AND outbound = 0{date_filter} "
                f"ORDER BY timestamp ASC"
            ),
            {"cid": connection_id, **date_params},
        )).fetchall()
        if not rows:
            rows = (await session.execute(
                _text(
                    f"SELECT phone, name, body, timestamp FROM messages "
                    f"WHERE connection_id = :eid AND outbound = 0{date_filter} "
                    f"ORDER BY timestamp ASC"
                ),
                {"eid": bot_id, **date_params},
            )).fetchall()

    if not rows:
        return {"processed": 0, "skipped": 0}

    from graphs.compiler import execute_flow
    from graphs.nodes.state import FlowState
    from datetime import datetime as _dt

    processed = 0
    skipped = 0

    for phone, name, body, ts_raw in rows:
        if not body or not body.strip():
            skipped += 1
            continue

        ts = None
        try:
            ts = _dt.fromisoformat(str(ts_raw))
        except (ValueError, TypeError):
            pass

        state = FlowState(
            message=body.strip(),
            message_type="text",
            connection_id=connection_id,
            canal=canal,
            bot_id=bot_id,
            contact_phone=phone,
            contact_name=name or phone,
            from_delta_sync=True,
            timestamp=ts,
        )
        await execute_flow(flow, state)
        processed += 1

    return {"processed": processed, "skipped": skipped}


class ApiTriggerBody(BaseModel):
    message: str = ""
    contact_phone: str = "api"
    contact_name: str = "API"


@router.post("/flows/{flow_id}/trigger/{node_id}")
async def trigger_flow(flow_id: str, node_id: str, body: ApiTriggerBody = None):
    """
    Dispara un flow desde un nodo api_trigger específico.

    La URL es única por nodo, lo que permite tener varios api_trigger
    en un mismo flow apuntando a distintas ramas.

    Retorna {ok: true, reply: "..."} o {ok: true, reply: null} si el flow
    no genera respuesta.
    """
    flow = await db.get_flow(flow_id)
    if not flow or not flow.get("active"):
        raise HTTPException(status_code=404, detail="Flow no encontrado o inactivo")

    nodes = flow.get("definition", {}).get("nodes", [])
    trigger_node = next((n for n in nodes if n.get("id") == node_id), None)
    if not trigger_node or trigger_node.get("type") != "api_trigger":
        raise HTTPException(status_code=404, detail="Nodo api_trigger no encontrado")

    if body is None:
        body = ApiTriggerBody()

    from graphs.compiler import execute_flow
    from graphs.nodes.state import FlowState

    state = FlowState(
        message=body.message,
        canal="api",
        contact_phone=body.contact_phone,
        contact_name=body.contact_name,
        bot_id=flow.get("bot_id", ""),
    )

    state = await execute_flow(flow, state, entry_node_id=node_id)
    return {"ok": True, "reply": state.reply}


@router.delete("/bots/{bot_id}/flows/{flow_id}", status_code=204)
async def delete_flow(
    bot_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_bot(bot_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    await db.delete_flow(flow_id)
    return Response(status_code=204)


@router.get("/bots/{bot_id}/google-accounts")
async def list_google_accounts(
    bot_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    """Lista las cuentas Google disponibles para la bot (propias + pulpo-default)."""
    _require_bot(bot_id, request, x_password)
    conns = await db.get_google_connections(bot_id)
    return [{"id": c["id"], "email": c["email"], "label": c["label"]} for c in conns]


# ─── Seed de flows por defecto ────────────────────────────────────────────────

_DEFAULT_FLOW_DEFINITION = {
    "nodes": [
        {"id": "message_trigger_1", "type": "message_trigger", "position": {"x": 250, "y": 50}, "config": {}},
    ],
    "edges": [],
    "viewport": {"x": 0, "y": 0, "zoom": 1},
}


async def seed_default_flows():
    """
    Si un bot no tiene flow, NO crea uno automáticamente.
    Un flow requiere connection_id explícito — no se puede inferir de forma segura.
    El usuario debe crear el flow desde el editor y asignarle una conexión.
    """
    pass
