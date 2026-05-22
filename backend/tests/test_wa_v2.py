"""
Tests para WhatsApp Trigger v2 (OpenWA).

Verifica que:
  - El endpoint /api/wa-v2/inbound acepta un webhook de OpenWA y responde 200
  - Los mensajes "fromMe=true" son ignorados (respuesta ok, sin crash)
  - GET /api/wa-v2/status responde con la lista de instancias
"""
import pytest
from conftest import BASE

_WEBHOOK_URL = f"{BASE}/api/wa-v2/inbound"
_STATUS_URL  = f"{BASE}/api/wa-v2/status"

_SAMPLE_PAYLOAD = {
    "from": "5491155612767@c.us",
    "body": "hola test",
    "type": "chat",
    "isGroupMsg": False,
    "sender": {"pushname": "TestUser"},
    "t": 1716400000,
    "fromMe": False,
    "sessionId": "5491100000000",
}


def test_inbound_ok(client):
    r = client.post("/api/wa-v2/inbound", json=_SAMPLE_PAYLOAD)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_inbound_from_me_ignored(client):
    payload = {**_SAMPLE_PAYLOAD, "fromMe": True}
    r = client.post("/api/wa-v2/inbound", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_status(client):
    from conftest import ADMIN
    r = client.get("/api/wa-v2/status", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert "instances" in data
    assert isinstance(data["instances"], list)
