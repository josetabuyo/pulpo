"""
Tests de flows: node-types, graph por empresa.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from graphs.node_types import NODE_TYPES, get as get_node_type, classify


ADMIN = {"x-password": "admin"}


# ─── node_types registry (unit, sin server) ──────────────────────────────────

def test_node_types_campos_obligatorios():
    for nt in NODE_TYPES.values():
        assert nt.id and nt.label and nt.color and nt.description

def test_classify_start_end():
    assert classify("__start__").id == "start"
    assert classify("__end__").id   == "end"

def test_classify_router():
    assert classify("scope_router").id == "router"

def test_classify_summarize():
    assert classify("summarizer_node").id == "summarize"

def test_classify_unknown_es_generic():
    assert classify("cualquier_cosa_rara").id == "generic"

def test_get_fallback_es_generic():
    assert get_node_type("tipo_inexistente").id == "generic"


# ─── GET /api/flow/node-types (público) ──────────────────────────────────────

def test_node_types_endpoint_ok(client):
    r = client.get("/api/flow/node-types")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == len(NODE_TYPES)

def test_node_types_endpoint_estructura(client):
    r = client.get("/api/flow/node-types")
    for nt in r.json():
        assert "id"          in nt
        assert "label"       in nt
        assert "color"       in nt
        assert "description" in nt

def test_node_types_endpoint_no_requiere_auth(client):
    """El catálogo es público — sin headers."""
    r = client.get("/api/flow/node-types")
    assert r.status_code == 200

def test_node_types_labels_vienen_del_registro(client):
    """Los labels del endpoint coinciden con el registro Python."""
    r = client.get("/api/flow/node-types")
    api_map = {nt["id"]: nt for nt in r.json()}
    for nt in NODE_TYPES.values():
        assert api_map[nt.id]["label"]       == nt.label
        assert api_map[nt.id]["color"]       == nt.color
        assert api_map[nt.id]["description"] == nt.description


def test_flow_graph_empresa_invalida(client):
    r = client.get("/api/empresas/no_existe/flow/graph", headers=ADMIN)
    assert r.status_code == 404


def test_flow_graph_requiere_auth(client):
    r = client.get("/api/empresas/bot_test/flow/graph")
    assert r.status_code in (401, 422)


def test_flow_graph_sintetico(client):
    """bot_test tiene tool_tipo=fixed_message → nodo reply."""
    r = client.get("/api/empresas/bot_test/flow/graph", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data
    node_ids = [n["id"] for n in data["nodes"]]
    assert "reply" in node_ids


def test_flow_graph_nodos_tienen_campos(client):
    r = client.get("/api/empresas/bot_test/flow/graph", headers=ADMIN)
    data = r.json()
    for node in data["nodes"]:
        assert "id" in node
        assert "label" in node
        assert "type" in node


def test_flow_graph_edges_tienen_campos(client):
    r = client.get("/api/empresas/bot_test/flow/graph", headers=ADMIN)
    data = r.json()
    for edge in data["edges"]:
        assert "source" in edge
        assert "target" in edge


def test_flow_graph_luganense_usa_langgraph(client):
    """luganense tiene flow_id=luganense → extrae grafo real."""
    r = client.get("/api/empresas/luganense/flow/graph", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    # El grafo de luganense tiene scope_router
    node_ids = [n["id"] for n in data["nodes"]]
    assert "scope_router" in node_ids
    assert "__start__" in node_ids
    assert "__end__" in node_ids


def test_flow_graph_luganense_tipos(client):
    """Los nodos de luganense se clasifican correctamente."""
    r = client.get("/api/empresas/luganense/flow/graph", headers=ADMIN)
    data = r.json()
    types_by_id = {n["id"]: n["type"] for n in data["nodes"]}
    assert types_by_id["__start__"] == "start"
    assert types_by_id["__end__"] == "end"
    assert types_by_id["scope_router"] == "router"


def test_flow_graph_luganense_edges_fork(client):
    """scope_router tiene dos salidas (noticias y oficio)."""
    r = client.get("/api/empresas/luganense/flow/graph", headers=ADMIN)
    data = r.json()
    from_router = [e for e in data["edges"] if e["source"] == "scope_router"]
    assert len(from_router) == 2


def test_flow_graph_fixed_message(client):
    """gm_herreria tiene tool_tipo=fixed_message → nodo reply."""
    r = client.get("/api/empresas/gm_herreria/flow/graph", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    node_ids = [n["id"] for n in data["nodes"]]
    assert "reply" in node_ids
    types_by_id = {n["id"]: n["type"] for n in data["nodes"]}
    assert types_by_id["reply"] == "reply"


def test_flow_graph_summarizer(client):
    """la_piquiteria tiene tool_tipo=summarizer → nodo summarize."""
    r = client.get("/api/empresas/la_piquiteria/flow/graph", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    node_ids = [n["id"] for n in data["nodes"]]
    assert "summarize" in node_ids
    types_by_id = {n["id"]: n["type"] for n in data["nodes"]}
    assert types_by_id["summarize"] == "summarize"


def test_flow_graph_todos_tienen_start_end(client):
    """Todos los grafos sintéticos tienen nodos __start__ y __end__."""
    for empresa in ("gm_herreria", "la_piquiteria", "bot_test"):
        r = client.get(f"/api/empresas/{empresa}/flow/graph", headers=ADMIN)
        node_ids = [n["id"] for n in r.json()["nodes"]]
        assert "__start__" in node_ids, f"{empresa} sin __start__"
        assert "__end__" in node_ids, f"{empresa} sin __end__"
