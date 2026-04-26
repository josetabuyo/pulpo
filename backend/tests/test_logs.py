"""Tests del endpoint /api/logs — feature monitoring."""
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import _FileLogFilter, _UvicornPollingFilter
from conftest import ADMIN


# ── Unit tests de filtros de log ───────────────────────────────────────────────

def _record(msg):
    r = logging.LogRecord(name="test", level=logging.INFO, pathname="", lineno=0,
                          msg=msg, args=(), exc_info=None)
    return r

class TestFileLogFilter:
    f = _FileLogFilter()

    def test_excluye_getUpdates(self):
        assert not self.f.filter(_record('HTTP Request: POST .../getUpdates "HTTP/1.1 200 OK"'))

    def test_excluye_no_new_updates(self):
        assert not self.f.filter(_record("No new updates found."))

    def test_excluye_calling_bot_api(self):
        assert not self.f.filter(_record("Calling Bot API endpoint `getUpdates` with parameters"))

    def test_excluye_call_to_bot_api(self):
        assert not self.f.filter(_record("Call to Bot API endpoint `getUpdates` finished"))

    def test_permite_mensaje_de_negocio(self):
        assert self.f.filter(_record("[empresa/tg-123] Mensaje de usuario: hola"))

    def test_permite_delta_sync(self):
        assert self.f.filter(_record("[delta-sync] Completado."))


class TestUvicornPollingFilter:
    f = _UvicornPollingFilter()

    def test_excluye_bots(self):
        assert not self.f.filter(_record('127.0.0.1 - "GET /api/bots HTTP/1.1" 200'))

    def test_excluye_sync_status(self):
        assert not self.f.filter(_record('127.0.0.1 - "GET /api/sync-status HTTP/1.1" 200'))

    def test_excluye_logs_latest(self):
        assert not self.f.filter(_record('127.0.0.1 - "GET /api/logs/latest?source=backend HTTP/1.1" 200'))

    def test_excluye_empresa_paused(self):
        assert not self.f.filter(_record('127.0.0.1 - "GET /api/empresa/gm_herreria/paused HTTP/1.1" 200'))

    def test_permite_mensaje_real(self):
        assert self.f.filter(_record('127.0.0.1 - "POST /api/whatsapp/send HTTP/1.1" 200'))

    def test_permite_health(self):
        assert self.f.filter(_record('127.0.0.1 - "GET /health HTTP/1.1" 200'))


def test_logs_latest_ok(client):
    r = client.get("/api/logs/latest?source=backend&lines=10", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert "lines" in body
    assert isinstance(body["lines"], list)
    assert body["source"] == "backend"


def test_logs_latest_respects_lines_param(client):
    r = client.get("/api/logs/latest?source=backend&lines=5", headers=ADMIN)
    assert r.status_code == 200
    assert len(r.json()["lines"]) <= 5


def test_logs_latest_default_source(client):
    r = client.get("/api/logs/latest", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["source"] == "backend"


def test_logs_latest_frontend_source(client):
    r = client.get("/api/logs/latest?source=frontend", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["source"] == "frontend"


def test_logs_latest_invalid_source(client):
    r = client.get("/api/logs/latest?source=inventado", headers=ADMIN)
    assert r.status_code == 400


def test_logs_latest_requires_auth(client):
    r = client.get("/api/logs/latest?source=backend")
    assert r.status_code == 422


def test_logs_latest_wrong_auth(client):
    r = client.get("/api/logs/latest?source=backend", headers={"x-password": "wrong"})
    assert r.status_code == 401


def test_logs_latest_contains_backend_entries(client):
    """El endpoint devuelve lista válida; si hay líneas, tienen formato de log."""
    r = client.get("/api/logs/latest?source=backend&lines=200", headers=ADMIN)
    lines = r.json()["lines"]
    assert isinstance(lines, list)
    # Si hay contenido, verificar que las líneas tienen formato de log esperado
    if lines:
        assert any("INFO" in l or "WARNING" in l or "ERROR" in l for l in lines)


def test_logs_stream_requires_auth(client):
    r = client.get("/api/logs/stream?source=backend", headers={"Accept": "text/event-stream"})
    assert r.status_code == 422
