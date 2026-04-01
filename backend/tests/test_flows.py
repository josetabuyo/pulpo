"""
Tests del endpoint GET /api/empresas/{empresa_id}/flow/graph
"""
import pytest


ADMIN = {"x-password": "admin"}


def test_flow_graph_empresa_invalida(client):
    r = client.get("/api/empresas/no_existe/flow/graph", headers=ADMIN)
    assert r.status_code == 404


def test_flow_graph_requiere_auth(client):
    r = client.get("/api/empresas/bot_test/flow/graph")
    assert r.status_code in (401, 422)


def test_flow_graph_sintetico(client):
    """bot_test no tiene flow_id → grafo sintético de assistant."""
    r = client.get("/api/empresas/bot_test/flow/graph", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0


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
