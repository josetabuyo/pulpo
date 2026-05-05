"""Tests de conexiones Google (google_connections)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx
from conftest import BASE, ADMIN_PASSWORD, ADMIN

EMPRESA_ID = "luganense"


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE, timeout=5)


# ─── Lista de conexiones ──────────────────────────────────────────────────────

def test_list_google_connections_sin_auth(client):
    r = client.get(f"/api/empresas/{EMPRESA_ID}/google-connections")
    assert r.status_code == 401


def test_list_google_connections_admin(client):
    r = client.get(f"/api/empresas/{EMPRESA_ID}/google-connections", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Debe incluir pulpo-default
    ids = [c["id"] for c in data]
    assert "pulpo-default" in ids


def test_pulpo_default_tiene_email(client):
    r = client.get(f"/api/empresas/{EMPRESA_ID}/google-connections", headers=ADMIN)
    assert r.status_code == 200
    pulpo = next((c for c in r.json() if c["id"] == "pulpo-default"), None)
    assert pulpo is not None
    assert "@" in pulpo["email"]
    assert pulpo["label"] == "Cuenta Pulpo"
    # No debe exponer credentials_json
    assert "credentials_json" not in pulpo


# ─── Crear conexión propia ────────────────────────────────────────────────────

_FAKE_SA = '{"client_email": "test@project.iam.gserviceaccount.com", "private_key": "-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKCAQEA\\n-----END RSA PRIVATE KEY-----\\n", "type": "service_account"}'


def test_create_google_connection_json_invalido(client):
    r = client.post(
        f"/api/empresas/{EMPRESA_ID}/google-connections",
        json={"credentials_json": "no-es-json"},
        headers=ADMIN,
    )
    assert r.status_code == 400


def test_create_google_connection_sin_campos(client):
    r = client.post(
        f"/api/empresas/{EMPRESA_ID}/google-connections",
        json={"credentials_json": '{"client_email": "x@y.com"}'},
        headers=ADMIN,
    )
    assert r.status_code == 400  # falta private_key


def test_create_y_delete_google_connection(client):
    # Crear
    r = client.post(
        f"/api/empresas/{EMPRESA_ID}/google-connections",
        json={"credentials_json": _FAKE_SA, "label": "Test SA"},
        headers=ADMIN,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["ok"] is True
    conn_id = data["id"]
    assert data["email"] == "test@project.iam.gserviceaccount.com"
    assert data["label"] == "Test SA"

    # Aparece en la lista
    r2 = client.get(f"/api/empresas/{EMPRESA_ID}/google-connections", headers=ADMIN)
    ids = [c["id"] for c in r2.json()]
    assert conn_id in ids

    # Eliminar
    r3 = client.delete(f"/api/empresas/{EMPRESA_ID}/google-connections/{conn_id}", headers=ADMIN)
    assert r3.status_code == 200
    assert r3.json()["ok"] is True

    # Ya no aparece
    r4 = client.get(f"/api/empresas/{EMPRESA_ID}/google-connections", headers=ADMIN)
    ids2 = [c["id"] for c in r4.json()]
    assert conn_id not in ids2


def test_delete_pulpo_default_prohibido(client):
    r = client.delete(
        f"/api/empresas/{EMPRESA_ID}/google-connections/pulpo-default",
        headers=ADMIN,
    )
    assert r.status_code == 403


# ─── google-accounts en flows ─────────────────────────────────────────────────

def test_google_accounts_endpoint(client):
    r = client.get(f"/api/empresas/{EMPRESA_ID}/google-accounts", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    pulpo = next((c for c in data if c["id"] == "pulpo-default"), None)
    assert pulpo is not None
    assert "id" in pulpo
    assert "email" in pulpo
    assert "label" in pulpo
    assert "credentials_json" not in pulpo
