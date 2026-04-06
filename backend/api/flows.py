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
