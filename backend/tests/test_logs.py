"""Tests del endpoint /api/logs — feature monitoring."""


def test_logs_latest_ok(client):
    r = client.get("/api/logs/latest?source=backend&lines=10", headers={"x-password": "admin"})
    assert r.status_code == 200
    body = r.json()
    assert "lines" in body
    assert isinstance(body["lines"], list)
    assert body["source"] == "backend"


def test_logs_latest_respects_lines_param(client):
    r = client.get("/api/logs/latest?source=backend&lines=5", headers={"x-password": "admin"})
    assert r.status_code == 200
    assert len(r.json()["lines"]) <= 5


def test_logs_latest_default_source(client):
    r = client.get("/api/logs/latest", headers={"x-password": "admin"})
    assert r.status_code == 200
    assert r.json()["source"] == "backend"


def test_logs_latest_frontend_source(client):
    r = client.get("/api/logs/latest?source=frontend", headers={"x-password": "admin"})
    assert r.status_code == 200
    assert r.json()["source"] == "frontend"


def test_logs_latest_invalid_source(client):
    r = client.get("/api/logs/latest?source=inventado", headers={"x-password": "admin"})
    assert r.status_code == 400


def test_logs_latest_requires_auth(client):
    r = client.get("/api/logs/latest?source=backend")
    assert r.status_code == 422


def test_logs_latest_wrong_auth(client):
    r = client.get("/api/logs/latest?source=backend", headers={"x-password": "wrong"})
    assert r.status_code == 401


def test_logs_latest_contains_backend_entries(client):
    """El log del backend debe tener al menos una línea de uvicorn."""
    r = client.get("/api/logs/latest?source=backend&lines=200", headers={"x-password": "admin"})
    lines = r.json()["lines"]
    assert len(lines) > 0
    # Al menos una línea debe tener INFO (uvicorn loguea así)
    assert any("INFO" in l for l in lines)


def test_logs_stream_requires_auth(client):
    r = client.get("/api/logs/stream?source=backend", headers={"Accept": "text/event-stream"})
    assert r.status_code == 422
