"""Tests de autenticación."""
import os
import pytest
from conftest import ADMIN, ADMIN_PASSWORD


def test_auth_ok(client):
    r = client.post("/api/auth", json={"password": ADMIN_PASSWORD})
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


@pytest.mark.skipif(
    os.getenv("ENABLE_BOTS", "true").lower() != "false",
    reason="Solo válido en servidores de desarrollo con ENABLE_BOTS=false",
)
def test_mode_is_sim(client):
    r = client.get("/api/mode", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["mode"] == "sim"


def test_protected_route_without_auth(client):
    r = client.get("/api/bots")
    assert r.status_code == 422  # falta header x-password


def test_protected_route_wrong_auth(client):
    r = client.get("/api/bots", headers={"x-password": "wrong"})
    assert r.status_code == 401
