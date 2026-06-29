"""
Tests de integración para el endpoint DELETE /api/connections/{number}.

Regresión del bug crítico del 2026-06-26:
  DELETE de una conexión WhatsApp eliminaba TODAS las bots que no tuvieran teléfonos,
  no solo la conexión específica. El filtro `[e for e in bots if e.get("phones")]`
  después del pop dejaba el config vacío.

Casos cubiertos:
  1. Eliminar el último teléfono de una bot → la bot sigue existiendo sin teléfonos
  2. Eliminar un teléfono de bot_A no afecta a bot_B que no tenía teléfonos
  3. Intentar eliminar un número inexistente → 404, ninguna bot eliminada
"""
import pytest
from conftest import ADMIN


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _create_bot(client, bot_id: str, name: str = None) -> None:
    r = client.post("/api/bots", headers=ADMIN, json={
        "id": bot_id,
        "name": name or bot_id,
        "password": "test_pass",
    })
    assert r.status_code in (201, 409), f"create_bot {bot_id}: {r.text}"


def _add_phone(client, bot_id: str, number: str) -> None:
    r = client.post("/api/connections", headers=ADMIN, json={
        "botId": bot_id,
        "number": number,
    })
    assert r.status_code == 201, f"add_phone {number} to {bot_id}: {r.text}"


def _delete_phone(client, number: str) -> int:
    r = client.delete(f"/api/connections/{number}", headers=ADMIN)
    return r.status_code


def _bot_exists(client, bot_id: str) -> bool:
    r = client.get("/api/bots", headers=ADMIN)
    assert r.status_code == 200
    return any(b["id"] == bot_id for b in r.json())


def _bot_phones(client, bot_id: str) -> list:
    r = client.get("/api/bots", headers=ADMIN)
    assert r.status_code == 200
    for b in r.json():
        if b["id"] == bot_id:
            return b["phones"]
    return []


# ─── Fixtures de limpieza ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def cleanup_test_bots(client):
    """Elimina las bots de prueba antes y después de cada test."""
    ids = ["conn_test_a", "conn_test_b"]
    for bot_id in ids:
        client.delete(f"/api/bots/{bot_id}", headers=ADMIN)
    yield
    for bot_id in ids:
        client.delete(f"/api/bots/{bot_id}", headers=ADMIN)


# ─── Tests de regresión ───────────────────────────────────────────────────────

def test_delete_last_phone_keeps_bot(client):
    """
    Regresión: eliminar el último teléfono de una bot no debe eliminar la bot.
    El bug filtraba 'if e.get("phones")' y borraba toda bot sin phones.
    """
    _create_bot(client, "conn_test_a")
    _add_phone(client, "conn_test_a", "5499000000001")

    status = _delete_phone(client, "5499000000001")
    assert status == 200, "DELETE de conexión debe retornar 200"

    assert _bot_exists(client, "conn_test_a"), (
        "La bot debe seguir existiendo aunque no tenga teléfonos"
    )
    phones = _bot_phones(client, "conn_test_a")
    assert phones == [], "La lista de teléfonos debe estar vacía después del DELETE"


def test_delete_phone_does_not_affect_phoneless_bot(client):
    """
    Regresión: eliminar el teléfono de bot_A no debe eliminar bot_B que no tenía teléfonos.
    """
    _create_bot(client, "conn_test_a")
    _add_phone(client, "conn_test_a", "5499000000002")

    _create_bot(client, "conn_test_b")  # bot sin teléfono

    _delete_phone(client, "5499000000002")

    assert _bot_exists(client, "conn_test_b"), (
        "bot_b (sin teléfonos) no debe ser eliminada al borrar el teléfono de bot_a"
    )
    assert _bot_exists(client, "conn_test_a"), (
        "bot_a tampoco debe desaparecer — la bot persiste aunque quede sin teléfonos"
    )


def test_delete_nonexistent_number_returns_404(client):
    """
    DELETE de un número que no existe debe retornar 404 y no modificar nada.
    """
    _create_bot(client, "conn_test_a")

    status = _delete_phone(client, "5499999999999")
    assert status == 404, "Número inexistente debe retornar 404"

    assert _bot_exists(client, "conn_test_a"), "La bot no debe ser afectada por un 404"


# ─── Tests de wavi_status (HTTP integration) ──────────────────────────────────

def test_phone_status_field_present_and_valid(client):
    """
    El status de un teléfono wavi debe ser un string válido.
    Regresión: antes siempre retornaba 'stopped' incluso cuando el daemon estaba activo,
    porque clients (para Telegram) nunca tenía entradas wavi.
    Ahora viene de wavi_status que se inicializa desde el daemon PID al startup.
    """
    _create_bot(client, "conn_test_a")
    _add_phone(client, "conn_test_a", "5490000000099")

    r = client.get("/api/bots", headers=ADMIN)
    assert r.status_code == 200
    phones = next(b["phones"] for b in r.json() if b["id"] == "conn_test_a")
    assert len(phones) == 1
    status = phones[0]["status"]
    # El status debe ser uno de los valores válidos de wavi_status
    assert status in ("stopped", "connecting", "ready", "disconnected"), (
        f"Status inesperado: {status!r}"
    )
    # Sin daemon corriendo para este número de prueba, debe ser 'stopped'
    assert status == "stopped"


def test_connections_endpoint_has_status_field(client):
    """
    El endpoint GET /api/connections debe incluir campo 'status' para phones wavi.
    """
    _create_bot(client, "conn_test_b")
    _add_phone(client, "conn_test_b", "5490000000098")

    r = client.get("/api/connections", headers=ADMIN)
    assert r.status_code == 200
    conns = [c for c in r.json() if c["number"] == "5490000000098"]
    assert conns, "La conexión debe aparecer en /connections"
    assert "status" in conns[0], "El endpoint connections debe incluir el campo status"
    assert conns[0]["status"] in ("stopped", "connecting", "ready", "disconnected")


def test_reconnect_wavi_returns_connecting_status(client):
    """
    POST /wavi/sessions/{session}/connect debe retornar status='connecting' de inmediato
    sin bloquear (el connect real ocurre en background).
    """
    session = "test-wavi-conn-99"

    r = client.post(f"/api/wavi/sessions/{session}/connect", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "connecting", (
        f"El reconectar debe responder 'connecting' de inmediato, got: {body}"
    )
    assert body["ok"] is True
    assert "qr_url" in body
