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



# ─── CRUD de flows ────────────────────────────────────────────────────────────

def test_list_flows_requiere_auth(client):
    r = client.get("/api/empresas/bot_test/flows")
    assert r.status_code in (401, 422)


def test_list_flows_empresa_invalida(client):
    r = client.get("/api/empresas/no_existe/flows", headers=ADMIN)
    assert r.status_code == 404


def test_list_flows_ok(client):
    r = client.get("/api/empresas/bot_test/flows", headers=ADMIN)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_flows_estructura(client):
    """Cada flow en la lista tiene los campos esperados (sin definition)."""
    r = client.get("/api/empresas/bot_test/flows", headers=ADMIN)
    for flow in r.json():
        assert "id"            in flow
        assert "empresa_id"    in flow
        assert "name"          in flow
        assert "active"        in flow
        assert "created_at"    in flow
        assert "definition" not in flow


def test_create_flow_ok(client):
    body = {"name": "Flow de prueba"}
    r = client.post("/api/empresas/bot_test/flows", json=body, headers=ADMIN)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Flow de prueba"
    assert data["empresa_id"] == "bot_test"
    assert "id" in data
    assert "definition" in data
    # limpiar
    client.delete(f"/api/empresas/bot_test/flows/{data['id']}", headers=ADMIN)


def test_create_flow_con_definition(client):
    definition = {
        "nodes": [{"id": "n1", "type": "reply", "position": {"x": 0, "y": 0}, "config": {"text": "Hola"}}],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    body = {"name": "Flow con nodos", "definition": definition}
    r = client.post("/api/empresas/bot_test/flows", json=body, headers=ADMIN)
    assert r.status_code == 201
    data = r.json()
    assert data["definition"]["nodes"][0]["config"]["text"] == "Hola"
    client.delete(f"/api/empresas/bot_test/flows/{data['id']}", headers=ADMIN)


def test_get_flow_ok(client):
    r_create = client.post("/api/empresas/bot_test/flows", json={"name": "Temp"}, headers=ADMIN)
    flow_id = r_create.json()["id"]

    r = client.get(f"/api/empresas/bot_test/flows/{flow_id}", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == flow_id
    assert "definition" in data

    client.delete(f"/api/empresas/bot_test/flows/{flow_id}", headers=ADMIN)


def test_get_flow_404(client):
    r = client.get("/api/empresas/bot_test/flows/no-existe-uuid", headers=ADMIN)
    assert r.status_code == 404


def test_get_flow_otra_empresa(client):
    """No debe devolver un flow de otra empresa."""
    r_create = client.post("/api/empresas/bot_test/flows", json={"name": "Privado"}, headers=ADMIN)
    flow_id = r_create.json()["id"]

    r = client.get(f"/api/empresas/gm_herreria/flows/{flow_id}", headers=ADMIN)
    assert r.status_code == 404

    client.delete(f"/api/empresas/bot_test/flows/{flow_id}", headers=ADMIN)


def test_update_flow_nombre(client):
    r_create = client.post("/api/empresas/bot_test/flows", json={"name": "Original"}, headers=ADMIN)
    flow_id = r_create.json()["id"]

    r = client.put(f"/api/empresas/bot_test/flows/{flow_id}", json={"name": "Renombrado"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["name"] == "Renombrado"

    client.delete(f"/api/empresas/bot_test/flows/{flow_id}", headers=ADMIN)


def test_update_flow_definition(client):
    r_create = client.post("/api/empresas/bot_test/flows", json={"name": "Edit"}, headers=ADMIN)
    flow_id = r_create.json()["id"]

    new_def = {
        "nodes": [{"id": "n1", "type": "reply", "position": {"x": 10, "y": 20}, "config": {"text": "Actualizado"}}],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    r = client.put(f"/api/empresas/bot_test/flows/{flow_id}", json={"definition": new_def}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["definition"]["nodes"][0]["config"]["text"] == "Actualizado"

    client.delete(f"/api/empresas/bot_test/flows/{flow_id}", headers=ADMIN)


def test_update_flow_404(client):
    r = client.put("/api/empresas/bot_test/flows/no-existe", json={"name": "x"}, headers=ADMIN)
    assert r.status_code == 404


def test_delete_flow_ok(client):
    r_create = client.post("/api/empresas/bot_test/flows", json={"name": "Borrar"}, headers=ADMIN)
    flow_id = r_create.json()["id"]

    r = client.delete(f"/api/empresas/bot_test/flows/{flow_id}", headers=ADMIN)
    assert r.status_code == 204

    r2 = client.get(f"/api/empresas/bot_test/flows/{flow_id}", headers=ADMIN)
    assert r2.status_code == 404


def test_delete_flow_404(client):
    r = client.delete("/api/empresas/bot_test/flows/no-existe", headers=ADMIN)
    assert r.status_code == 404


def test_seed_flows_existe_luganense(client):
    """El seed automático crea un flow para luganense en el arranque."""
    r = client.get("/api/empresas/luganense/flows", headers=ADMIN)
    assert r.status_code == 200
    flows = r.json()
    assert len(flows) >= 1


def test_seed_flow_luganense_tiene_nodos(client):
    """El flow seedeado de luganense tiene definition con nodos."""
    r = client.get("/api/empresas/luganense/flows", headers=ADMIN)
    flow_id = r.json()[0]["id"]
    r2 = client.get(f"/api/empresas/luganense/flows/{flow_id}", headers=ADMIN)
    definition = r2.json()["definition"]
    assert len(definition["nodes"]) > 0
    assert len(definition["edges"]) > 0
