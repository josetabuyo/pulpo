"""
API REST de flows (grafos de agente).

GET /api/empresas/{empresa_id}/flow/graph
→ { nodes: [{id, label, type}], edges: [{source, target, label?}] }
"""
import os
from fastapi import APIRouter, HTTPException, Request
from fastapi import Header
from typing import Optional

import db
from config import load_config
from middleware_auth import get_empresa_bot_id

router = APIRouter()

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# ─── Grafos sintéticos (Opción B de Fase 1) ────────────────────────────────────

_SYNTHETIC = {
    "fixed_message": {
        "nodes": [
            {"id": "__start__", "label": "Inicio", "type": "start"},
            {"id": "reply",     "label": "Mensaje fijo", "type": "reply"},
            {"id": "__end__",   "label": "Fin", "type": "end"},
        ],
        "edges": [
            {"source": "__start__", "target": "reply",   "label": None},
            {"source": "reply",     "target": "__end__", "label": None},
        ],
    },
    "summarizer": {
        "nodes": [
            {"id": "__start__",  "label": "Inicio",       "type": "start"},
            {"id": "summarize",  "label": "Sumarizador",  "type": "summarize"},
            {"id": "__end__",    "label": "Fin",          "type": "end"},
        ],
        "edges": [
            {"source": "__start__", "target": "summarize", "label": None},
            {"source": "summarize", "target": "__end__",   "label": None},
        ],
    },
    "assistant": {
        "nodes": [
            {"id": "__start__",  "label": "Inicio",        "type": "start"},
            {"id": "assistant",  "label": "Asistente LLM", "type": "llm"},
            {"id": "__end__",    "label": "Fin",           "type": "end"},
        ],
        "edges": [
            {"source": "__start__", "target": "assistant", "label": None},
            {"source": "assistant", "target": "__end__",   "label": None},
        ],
    },
}

# ─── Clasificador de nodos ──────────────────────────────────────────────────────

def _classify_node(name: str) -> str:
    if name in ("__start__",):
        return "start"
    if name in ("__end__",):
        return "end"
    if "router" in name or "classify" in name:
        return "router"
    if "fetch" in name or "scrape" in name:
        return "fetch"
    if "noticias" in name or "llm" in name or "respond" in name or "assistant" in name:
        return "llm"
    if "oficio" in name or "reply" in name or "fixed" in name:
        return "reply"
    if "notify" in name:
        return "notify"
    if "summar" in name:
        return "summarize"
    return "generic"


def _node_label(name: str) -> str:
    """Convierte node_id a etiqueta legible."""
    if name == "__start__":
        return "Inicio"
    if name == "__end__":
        return "Fin"
    return name.replace("_", " ")


# ─── Extraer grafo desde módulo LangGraph ───────────────────────────────────────

def _graph_from_module(flow_id: str) -> dict:
    if flow_id == "luganense":
        from graphs.luganense import app
        g = app.get_graph()
        nodes = [
            {"id": n, "label": _node_label(n), "type": _classify_node(n)}
            for n in g.nodes
        ]
        edges = [
            {"source": e.source, "target": e.target, "label": getattr(e, "data", None)}
            for e in g.edges
        ]
        return {"nodes": nodes, "edges": edges}
    raise ValueError(f"flow_id desconocido: {flow_id}")


# ─── Auth helpers ───────────────────────────────────────────────────────────────

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


# ─── Endpoint ───────────────────────────────────────────────────────────────────

@router.get("/empresas/{empresa_id}/flow/graph")
async def get_flow_graph(
    empresa_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    bot = _require_empresa(empresa_id, request, x_password)

    flow_id = bot.get("flow_id")

    # Si la empresa tiene flow_id → extraer grafo real de LangGraph
    if flow_id:
        try:
            return _graph_from_module(flow_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al leer grafo: {e}")

    # Sin flow_id → grafo sintético
    # 1. Buscar primera herramienta activa en DB
    tools = await db.get_tools(empresa_id)
    active = next((t for t in tools if t.get("activa")), None)
    if active:
        tool_tipo = active["tipo"]
    else:
        # 2. Fallback a phones.json (campo tool_tipo)
        tool_tipo = bot.get("tool_tipo") or "assistant"
    graph = _SYNTHETIC.get(tool_tipo, _SYNTHETIC["assistant"])
    return graph
