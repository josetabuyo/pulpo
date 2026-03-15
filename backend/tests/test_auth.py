"""Tests de autenticación — olvidados antes."""


def test_auth_ok(client):
    r = client.post("/api/auth", json={"password": "admin"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["role"] == "admin"


def test_auth_wrong_password(client):
    r = client.post("/api/auth", json={"password": "bad"})
    assert r.status_code == 401


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_mode_is_sim(client):
    r = client.get("/api/mode", headers={"x-password": "admin"})
    assert r.status_code == 200
    assert r.json()["mode"] == "sim"


def test_protected_route_without_auth(client):
    r = client.get("/api/bots")
    assert r.status_code == 422  # falta header x-password


def test_protected_route_wrong_auth(client):
    r = client.get("/api/bots", headers={"x-password": "wrong"})
    assert r.status_code == 401
