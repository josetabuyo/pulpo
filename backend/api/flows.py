"""
API REST de flows (grafos de agente).

GET    /api/flow/node-types                      → catálogo de tipos de nodo (público)
GET    /api/empresas/{id}/flow/graph             → grafo de la empresa para visualización (auth)
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
from graphs.node_types import NODE_TYPES, get as get_node_type, classify

router = APIRouter()

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# ─── Grafos sintéticos por tipo de tool ─────────────────────────────────────
# Cada entrada: lista de (node_id, type_id). Labels y colores vienen del registro.

_SYNTHETIC_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "fixed_message": [
        ("__start__", "start"),
        ("reply",     "reply"),
        ("__end__",   "end"),
    ],
    "summarizer": [
        ("__start__",  "start"),
        ("summarize",  "summarize"),
        ("__end__",    "end"),
    ],
    "assistant": [
        ("__start__",  "start"),
        ("assistant",  "llm"),
        ("__end__",    "end"),
    ],
    "flow": [
        ("__start__",  "start"),
        ("flow",       "generic"),
        ("__end__",    "end"),
    ],
}

_SYNTHETIC_EDGES: dict[str, list[tuple[str, str]]] = {
    "fixed_message": [("__start__", "reply"),     ("reply",      "__end__")],
    "summarizer":    [("__start__", "summarize"), ("summarize",  "__end__")],
    "assistant":     [("__start__", "assistant"), ("assistant",  "__end__")],
    "flow":          [("__start__", "flow"),      ("flow",       "__end__")],
}


def _build_synthetic(tool_tipo: str) -> dict:
    template = _SYNTHETIC_TEMPLATES.get(tool_tipo, _SYNTHETIC_TEMPLATES["assistant"])
    edge_defs = _SYNTHETIC_EDGES.get(tool_tipo, _SYNTHETIC_EDGES["assistant"])
    nodes = [
        {"id": nid, "label": get_node_type(ntype).label, "type": ntype}
        for nid, ntype in template
    ]
    edges = [
        {"source": src, "target": tgt, "label": None}
        for src, tgt in edge_defs
    ]
    return {"nodes": nodes, "edges": edges}


# ─── Helpers de etiquetas ────────────────────────────────────────────────────

_ACRONYMS = {"fb", "llm", "api", "url", "id"}

def _node_label(node_id: str) -> str:
    """
    Convierte un node_id de LangGraph en una etiqueta legible.
    El node_id es la fuente de verdad del nombre del nodo — no el tipo genérico.
      buscar_posts_fb   → "Buscar posts FB"
      responder_noticias → "Responder noticias"
      scope_router       → "Scope router"
    """
    if node_id == "__start__":
        return "Inicio"
    if node_id == "__end__":
        return "Fin"
    parts = node_id.split("_")
    return " ".join(
        w.upper() if w in _ACRONYMS else (w.capitalize() if i == 0 else w)
        for i, w in enumerate(parts)
    )


# ─── Extractor de grafo LangGraph ────────────────────────────────────────────

def _graph_from_module(flow_id: str) -> dict:
    if flow_id == "luganense":
        from graphs.luganense import app
        g = app.get_graph()
        nodes = [
            {
                "id": n,
                "label": _node_label(n),
                "type": classify(n).id,
                "description": classify(n).description,
            }
            for n in g.nodes
        ]
        edges = [
            {"source": e.source, "target": e.target, "label": getattr(e, "data", None)}
            for e in g.edges
        ]
        return {"nodes": nodes, "edges": edges}
    raise ValueError(f"flow_id desconocido: {flow_id}")


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

async def seed_default_flows():
    """
    Crea flows iniciales en DB si no existen todavía.
    Se llama una vez en el lifespan del servidor.
    """
    from config import load_config as _load_config
    config = _load_config()

    for bot in config.get("bots", []):
        empresa_id = bot["id"]
        if await db.flow_exists_for_empresa(empresa_id):
            continue

        flow_id = bot.get("flow_id")
        if flow_id:
            # Empresa con grafo LangGraph real → extraer nodos/edges y guardar
            try:
                graph_data = _graph_from_module(flow_id)
                definition = {
                    "nodes": [
                        {
                            "id": n["id"],
                            "type": n["type"],
                            "position": {"x": 0, "y": 0},
                            "config": {},
                        }
                        for n in graph_data["nodes"]
                    ],
                    "edges": [
                        {
                            "id": f"e_{e['source']}_{e['target']}",
                            "source": e["source"],
                            "target": e["target"],
                            "label": e.get("label"),
                        }
                        for e in graph_data["edges"]
                    ],
                    "viewport": {"x": 0, "y": 0, "zoom": 1},
                }
                await db.create_flow(empresa_id, bot.get("name", empresa_id), definition)
            except Exception:
                pass  # Si falla el import del grafo, no bloquear el arranque
        else:
            # Empresa con tool_tipo → flow sintético de 1 nodo
            tool_tipo = bot.get("tool_tipo") or "assistant"
            tipo_a_nodo = {
                "fixed_message": "reply",
                "summarizer":    "summarize",
                "assistant":     "llm_respond",
                "flow":          "llm_respond",
            }
            node_type = tipo_a_nodo.get(tool_tipo, "llm_respond")
            definition = {
                "nodes": [
                    {"id": "__start__",  "type": "start",    "position": {"x": 250, "y": 50},  "config": {}},
                    {"id": "main_node", "type": node_type,  "position": {"x": 250, "y": 200}, "config": {}},
                    {"id": "__end__",   "type": "end",      "position": {"x": 250, "y": 350}, "config": {}},
                ],
                "edges": [
                    {"id": "e_start_main", "source": "__start__",  "target": "main_node", "label": None},
                    {"id": "e_main_end",   "source": "main_node", "target": "__end__",   "label": None},
                ],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            }
            await db.create_flow(empresa_id, bot.get("name", empresa_id), definition)


@router.get("/empresas/{empresa_id}/flow/graph")
async def get_flow_graph(
    empresa_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    bot = _require_empresa(empresa_id, request, x_password)

    flow_id = bot.get("flow_id")
    if flow_id:
        try:
            return _graph_from_module(flow_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al leer grafo: {e}")

    tools = await db.get_tools(empresa_id)
    active = next((t for t in tools if t.get("activa")), None)
    tool_tipo = active["tipo"] if active else bot.get("tool_tipo") or "assistant"
    return _build_synthetic(tool_tipo)
