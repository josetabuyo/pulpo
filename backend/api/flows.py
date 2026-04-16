"""
API REST de flows (grafos de agente).

GET    /api/flow/node-types                      → catálogo de tipos de nodo (público)
GET    /api/empresas/{id}/flows                  → lista de flows de la empresa (auth)
POST   /api/empresas/{id}/flows                  → crear flow (auth)
GET    /api/empresas/{id}/flows/{flow_id}        → detalle con definition (auth)
PUT    /api/empresas/{id}/flows/{flow_id}        → actualizar (auth)
DELETE /api/empresas/{id}/flows/{flow_id}        → eliminar (auth)
"""
import os
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi import Header
from pydantic import BaseModel
from typing import Optional

import db
from config import load_config
from middleware_auth import get_empresa_id_from_token
from graphs.node_types import NODE_TYPES
from graphs.nodes import NODE_REGISTRY

router = APIRouter()

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _require_empresa(empresa_id: str, request: Request, x_password: Optional[str]) -> dict:
    config = load_config()
    bot = next((b for b in config.get("empresas", []) if b["id"] == empresa_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if x_password and x_password == _ADMIN_PASSWORD:
        return bot
    token_empresa_id = get_empresa_id_from_token(request)
    if not token_empresa_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    if token_empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
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
        result.append({
            "id":          nt.id,
            "label":       nt.label,
            "color":       nt.color,
            "description": nt.description,
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


# ─── Endpoints de flows CRUD ──────────────────────────────────────────────────

@router.get("/empresas/{empresa_id}/flows")
async def list_flows(
    empresa_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    return await db.get_flows(empresa_id)


@router.post("/empresas/{empresa_id}/flows", status_code=201)
async def create_flow(
    empresa_id: str,
    body: FlowIn,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    try:
        flow_id = await db.create_flow(
            empresa_id=empresa_id,
            name=body.name,
            definition=body.definition,
            connection_id=body.connection_id,
            contact_phone=body.contact_phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await db.get_flow(flow_id)


@router.get("/empresas/{empresa_id}/flows/{flow_id}")
async def get_flow(
    empresa_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    return flow


@router.put("/empresas/{empresa_id}/flows/{flow_id}")
async def update_flow(
    empresa_id: str,
    flow_id: str,
    body: FlowUpdate,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
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


@router.get("/empresas/{empresa_id}/flows/has-node/{node_type}")
async def has_node_type(
    empresa_id: str,
    node_type: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    """Devuelve {found: bool} indicando si algún flow de la empresa contiene el tipo de nodo."""
    _require_empresa(empresa_id, request, x_password)
    found = await db.empresa_has_node_type(empresa_id, node_type)
    return {"found": found}


@router.post("/empresas/{empresa_id}/flows/{flow_id}/replay")
async def replay_flow(
    empresa_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    """
    Delta-sync: recorre los mensajes de la DB del connection_id del trigger
    (de más nuevo a más viejo) y ejecuta el flow completo para cada uno,
    con from_delta_sync=True (los nodos de reply/llm no envían nada).
    Se detiene al llegar al timestamp del mensaje más antiguo ya procesado
    por el flow (dedup por hash en summarize, sin-respuesta en reply).

    Solo aplica a flows con trigger whatsapp_trigger o telegram_trigger.
    """
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")

    # Encontrar el nodo trigger y su connection_id + canal
    nodes = flow.get("definition", {}).get("nodes", [])
    trigger = next(
        (n for n in nodes if n.get("type") in ("whatsapp_trigger", "telegram_trigger", "message_trigger")),
        None,
    )
    if not trigger:
        raise HTTPException(status_code=400, detail="El flow no tiene un nodo trigger de mensajes")

    trigger_type = trigger.get("type", "")
    connection_id = trigger.get("config", {}).get("connection_id", "")
    if not connection_id:
        raise HTTPException(status_code=400, detail="El trigger no tiene connection_id configurado")

    canal = "telegram" if trigger_type == "telegram_trigger" else "whatsapp"

    # Leer mensajes de DB ordenados de más nuevo a más viejo
    from db import AsyncSessionLocal, text as _text
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            _text(
                "SELECT phone, name, body, timestamp FROM messages "
                "WHERE connection_id = :cid AND outbound = 0 "
                "ORDER BY timestamp DESC"
            ),
            {"cid": connection_id},
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
            empresa_id=empresa_id,
            contact_phone=phone,
            contact_name=name or phone,
            from_delta_sync=True,
            timestamp=ts,
        )
        await execute_flow(flow, state)
        processed += 1

    return {"processed": processed, "skipped": skipped}


@router.delete("/empresas/{empresa_id}/flows/{flow_id}", status_code=204)
async def delete_flow(
    empresa_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    await db.delete_flow(flow_id)
    return Response(status_code=204)


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
