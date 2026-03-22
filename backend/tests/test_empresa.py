"""Tests del portal de empresa — con JWT Bearer tokens."""
import pytest

ADMIN = {"x-password": "admin"}

BOT_ID  = "bot_test"
BOT_PWD = "bot_test"


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
    token = _get_token(client)
    r = client.get(f"/api/empresa/{BOT_ID}", headers=_auth(token))
    conns = r.json()["connections"]
    assert len(conns) > 0
    for c in conns:
        assert "id" in c
        assert c["type"] in ("whatsapp", "telegram")
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



def test_empresa_connect_sim(client):
    """En modo sim, connect devuelve status ready inmediatamente."""
    token = _get_token(client)
    conns = client.get(f"/api/empresa/{BOT_ID}", headers=_auth(token)).json()["connections"]
    wa_conns = [c for c in conns if c["type"] == "whatsapp"]
    if not wa_conns:
        return
    number = wa_conns[0]["id"]

    r = client.post(f"/api/empresa/{BOT_ID}/connect/{number}", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["sessionId"] == number


def test_empresa_disconnect_sim(client):
    """Disconnect en modo sim → ok."""
    token = _get_token(client)
    conns = client.get(f"/api/empresa/{BOT_ID}", headers=_auth(token)).json()["connections"]
    wa_conns = [c for c in conns if c["type"] == "whatsapp"]
    if not wa_conns:
        return
    number = wa_conns[0]["id"]

    r = client.post(f"/api/empresa/{BOT_ID}/disconnect/{number}", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["ok"] is True

    client.post(f"/api/empresa/{BOT_ID}/connect/{number}", headers=_auth(token))


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
