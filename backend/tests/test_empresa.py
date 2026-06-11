"""Tests del portal de empresa — con JWT Bearer tokens."""
import pytest
from conftest import ADMIN, TEST_BOT_ID as BOT_ID, TEST_BOT_PWD as BOT_PWD


def _get_token(client):
    """Login JWT y devuelve access_token."""
    r = client.post("/api/empresa/login", json={"bot_id": BOT_ID, "password": BOT_PWD})
    assert r.status_code == 200, f"Login falló: {r.text}"
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Auth ────────────────────────────────────────────────────────

def test_empresa_auth_wrong_password(client):
    r = client.post("/api/empresa/auth", json={"password": "clave_incorrecta_xyz"})
    assert r.status_code == 401


def test_empresa_auth_missing_body(client):
    r = client.post("/api/empresa/auth", json={})
    assert r.status_code == 422


def test_empresa_auth_ok(client):
    r = client.post("/api/empresa/auth", json={"password": BOT_PWD})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["bot_id"] == BOT_ID
    assert isinstance(body["bot_name"], str)


# ─── Login JWT ───────────────────────────────────────────────────

def test_empresa_login_wrong_password(client):
    r = client.post("/api/empresa/login", json={"bot_id": BOT_ID, "password": "mala"})
    assert r.status_code == 401


def test_empresa_login_ok(client):
    r = client.post("/api/empresa/login", json={"bot_id": BOT_ID, "password": BOT_PWD})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["bot_id"] == BOT_ID


def test_empresa_me(client):
    token = _get_token(client)
    r = client.get("/api/empresa/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["bot_id"] == BOT_ID


def test_empresa_me_invalid_token(client):
    r = client.get("/api/empresa/me", headers={"Authorization": "Bearer INVALID"})
    assert r.status_code == 401


# ─── Endpoints con auth JWT ──────────────────────────────────────

def test_empresa_get_ok(client):
    token = _get_token(client)
    r = client.get(f"/api/empresa/{BOT_ID}", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["bot_id"] == BOT_ID
    assert isinstance(body["bot_name"], str)
    assert isinstance(body["connections"], list)


def test_empresa_get_connections_structure(client):
    """Valida la forma de cada conexión. bot_test puede no tener ninguna
    (en producción se crea vacío), por eso no se exige un mínimo."""
    token = _get_token(client)
    r = client.get(f"/api/empresa/{BOT_ID}", headers=_auth(token))
    conns = r.json()["connections"]
    assert isinstance(conns, list)
    for c in conns:
        assert "id" in c
        assert c["type"] == "telegram"
        assert "status" in c


def test_empresa_get_wrong_auth(client):
    r = client.get(f"/api/empresa/{BOT_ID}", headers={"Authorization": "Bearer INVALID"})
    assert r.status_code == 401


def test_empresa_get_wrong_bot_id(client):
    """Token de bot_test, pero accediendo a otro bot → 403."""
    token = _get_token(client)
    r = client.get("/api/empresa/otro_bot_id", headers=_auth(token))
    assert r.status_code == 403


def test_empresa_get_no_auth(client):
    r = client.get(f"/api/empresa/{BOT_ID}")
    assert r.status_code == 401





# ─── Refresh + Logout ────────────────────────────────────────────

def test_empresa_refresh_and_logout(client):
    """Login → refresh → logout → refresh falla."""
    # Login
    r = client.post("/api/empresa/login", json={"bot_id": BOT_ID, "password": BOT_PWD})
    assert r.status_code == 200
    cookies = r.cookies

    # Refresh
    r2 = client.post("/api/empresa/refresh", cookies=cookies)
    assert r2.status_code == 200
    assert "access_token" in r2.json()

    # Logout
    r3 = client.post("/api/empresa/logout", cookies=cookies)
    assert r3.status_code == 200
    assert r3.json()["ok"] is True

    # Refresh después de logout → 401
    r4 = client.post("/api/empresa/refresh", cookies=cookies)
    assert r4.status_code == 401
