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
from middleware_auth import get_empresa_bot_id
from graphs.node_types import NODE_TYPES

router = APIRouter()

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _require_empresa(empresa_id: str, request: Request, x_password: Optional[str]) -> dict:
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == empresa_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if x_password and x_password == _ADMIN_PASSWORD:
        return bot
    token_bot_id = get_empresa_bot_id(request)
    if not token_bot_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    if token_bot_id != empresa_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
    return bot


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/flow/node-types")
def list_node_types():
    """Catálogo público de tipos de nodo: id, label, color, description."""
    return [
        {"id": nt.id, "label": nt.label, "color": nt.color, "description": nt.description}
        for nt in NODE_TYPES.values()
    ]


# ─── Schemas ─────────────────────────────────────────────────────────────────

class FlowIn(BaseModel):
    name: str
    definition: dict | None = None
    connection_id: str | None = None
    contact_phone: str | None = None


class FlowUpdate(BaseModel):
    name: str | None = None
    definition: dict | None = None
    connection_id: str | None = None
    contact_phone: str | None = None
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
    flow_id = await db.create_flow(
        empresa_id=empresa_id,
        name=body.name,
        definition=body.definition,
        connection_id=body.connection_id,
        contact_phone=body.contact_phone,
    )
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
    if updates:
        await db.update_flow(flow_id, **updates)
    return await db.get_flow(flow_id)


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
        {"id": "__start__", "type": "start", "position": {"x": 250, "y": 50},  "config": {}},
        {"id": "__end__",   "type": "end",   "position": {"x": 250, "y": 200}, "config": {}},
    ],
    "edges": [
        {"id": "e1", "source": "__start__", "target": "__end__", "label": None},
    ],
    "viewport": {"x": 0, "y": 0, "zoom": 1},
}


async def seed_default_flows():
    """Si un bot no tiene flow, crea uno vacío (start → end)."""
    from config import load_config as _load_config
    config = _load_config()
    for bot in config.get("bots", []):
        empresa_id = bot["id"]
        if not await db.flow_exists_for_empresa(empresa_id):
            await db.create_flow(empresa_id, bot.get("name", empresa_id), _DEFAULT_FLOW_DEFINITION)
