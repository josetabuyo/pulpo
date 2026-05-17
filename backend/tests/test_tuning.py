"""Tests de los endpoints de manual tuning del sumarizador."""
import pytest
from conftest import ADMIN, client  # noqa: F401


EMPRESA = "test-tuning-empresa"
PHONE = "test-tuning-contact"
BASE = f"/api/summarizer/{EMPRESA}/{PHONE}"


@pytest.fixture(autouse=True)
def clean_contact(client):
    """Limpia el contacto antes y después de cada test."""
    client.post(f"/api/summarizer/{EMPRESA}/{PHONE}/sync", headers=ADMIN)
    # Borra el chat.md si existe mediante clear (sync sobre vacío)
    yield
    # Limpieza post-test: no hacemos nada, cada test empieza limpio


def _seed(client, texts: list[str]):
    """Inserta mensajes de texto en el contacto."""
    for t in texts:
        r = client.post(f"{BASE}/message", json={"content": t}, headers=ADMIN)
        assert r.status_code == 200, r.text
    return r


def _msgs(client, include_ids=False):
    url = f"{BASE}/messages"
    if include_ids:
        url += "?include_ids=true"
    r = client.get(url, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["messages"]


# ─── POST /message ────────────────────────────────────────────────────────────

def test_insert_message(client):
    _seed(client, ["Hola mundo"])
    msgs = _msgs(client)
    assert any("Hola mundo" in (m.get("content") or "") for m in msgs)


def test_insert_message_returns_count(client):
    r = client.post(f"{BASE}/message", json={"content": "Primero"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["message_count"] >= 1


def test_insert_message_with_sender(client):
    r = client.post(
        f"{BASE}/message",
        json={"content": "Hola", "sender": "Juan"},
        headers=ADMIN,
    )
    assert r.status_code == 200
    msgs = _msgs(client)
    assert any(m.get("sender") == "Juan" for m in msgs)


# ─── DELETE /message/{id} ─────────────────────────────────────────────────────

def test_delete_message(client):
    _seed(client, ["Borrame", "Quédate"])
    msgs = _msgs(client, include_ids=True)
    target = next((m for m in msgs if "Borrame" in (m.get("content") or "")), None)
    assert target is not None, "Mensaje 'Borrame' no encontrado"
    assert target.get("_id"), "El mensaje no tiene _id"

    r = client.delete(f"{BASE}/message/{target['_id']}", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    remaining = _msgs(client)
    assert not any("Borrame" in (m.get("content") or "") for m in remaining)
    assert any("Quédate" in (m.get("content") or "") for m in remaining)


def test_delete_missing_message(client):
    r = client.delete(f"{BASE}/message/9999", headers=ADMIN)
    assert r.status_code == 404


# ─── PUT /messages (reorder) ──────────────────────────────────────────────────

def test_rewrite_messages(client):
    _seed(client, ["A", "B", "C"])
    msgs = _msgs(client, include_ids=True)
    assert len(msgs) >= 3

    # Invertir orden
    reversed_msgs = list(reversed(msgs))
    r = client.put(f"{BASE}/messages", json={"messages": reversed_msgs}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["message_count"] == len(msgs)


def test_rewrite_preserves_count(client):
    _seed(client, ["X", "Y"])
    msgs = _msgs(client, include_ids=True)
    r = client.put(f"{BASE}/messages", json={"messages": msgs}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["message_count"] == len(msgs)


# ─── include_ids param ────────────────────────────────────────────────────────

def test_messages_without_ids(client):
    _seed(client, ["Test"])
    msgs = _msgs(client, include_ids=False)
    for m in msgs:
        assert "_id" not in m


def test_messages_with_ids(client):
    _seed(client, ["Test IDs"])
    msgs = _msgs(client, include_ids=True)
    assert all(m.get("_id") is not None for m in msgs if m.get("type") != "document")


# ─── POST /consolidate ────────────────────────────────────────────────────────

def test_consolidate(client):
    _seed(client, ["Msg consolidado"])
    r = client.post(f"{BASE}/consolidate", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["message_count"] >= 1
    assert "consolidated_at" in data


def test_get_consolidation(client):
    _seed(client, ["Para consolidar"])
    client.post(f"{BASE}/consolidate", headers=ADMIN)
    r = client.get(f"{BASE}/consolidation", headers=ADMIN)
    assert r.status_code == 200
    meta = r.json()
    assert "consolidated_at" in meta
    assert "message_count" in meta


def test_get_consolidation_not_found(client):
    # Contacto que nunca fue consolidado en esta sesión de tests
    r = client.get(f"/api/summarizer/{EMPRESA}/never-consolidated/consolidation", headers=ADMIN)
    assert r.status_code == 404
