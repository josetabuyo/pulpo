"""
Tests de la API de contactos y lógica de canales.
Requiere servidor corriendo (BACKEND_PORT en .env).
"""
import time
from conftest import get_bot_token

BOT_ID  = "bot_test"
BOT_PWD = "bot_test"


def _uniq_phone(base="549100"):
    """Genera un número único basado en timestamp para evitar colisiones de UNIQUE(type,value)."""
    return f"{base}{int(time.time() * 1000) % 10_000_000:07d}"


# ─── CRUD contactos ───────────────────────────────────────────────

def test_list_contacts_empty(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    r = client.get(f"/api/bots/{BOT_ID}/contacts", headers=auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_contact(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    r = client.post(f"/api/bots/{BOT_ID}/contacts",
                    json={"name": "Test Contact", "channels": []},
                    headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Test Contact"
    assert body["connection_id"] == BOT_ID
    assert isinstance(body["channels"], list)
    # Cleanup
    client.delete(f"/api/contacts/{body['id']}", headers=auth)


def test_create_contact_with_channels(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    r = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Con Canales",
        "channels": [{"type": "telegram", "value": "@testcanal"}],
    }, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert len(body["channels"]) == 1
    assert body["channels"][0]["type"] == "telegram"
    assert body["channels"][0]["value"] == "@testcanal"
    client.delete(f"/api/contacts/{body['id']}", headers=auth)


def test_get_contact(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    create = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Get Test"}, headers=auth).json()
    r = client.get(f"/api/contacts/{create['id']}", headers=auth)
    assert r.status_code == 200
    assert r.json()["id"] == create["id"]
    client.delete(f"/api/contacts/{create['id']}", headers=auth)


def test_update_contact(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    create = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Old Name"}, headers=auth).json()
    r = client.put(f"/api/contacts/{create['id']}", json={"name": "New Name"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    client.delete(f"/api/contacts/{create['id']}", headers=auth)


def test_delete_contact(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    create = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Delete Me"}, headers=auth).json()
    r = client.delete(f"/api/contacts/{create['id']}", headers=auth)
    assert r.status_code == 204
    r2 = client.get(f"/api/contacts/{create['id']}", headers=auth)
    assert r2.status_code == 404


def test_contact_not_found(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    r = client.get("/api/contacts/999999", headers=auth)
    assert r.status_code == 404


# ─── Canales ──────────────────────────────────────────────────────

def test_add_and_delete_channel(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Channel Test"}, headers=auth).json()
    # Agregar canal
    r = client.post(f"/api/contacts/{c['id']}/channels",
                    json={"type": "telegram", "value": "@testuser"},
                    headers=auth)
    assert r.status_code == 201
    ch_id = r.json()["id"]
    # Verificar que aparece en el contacto
    r2 = client.get(f"/api/contacts/{c['id']}", headers=auth)
    channels = r2.json()["channels"]
    assert any(ch["id"] == ch_id for ch in channels)
    # Eliminar canal
    r3 = client.delete(f"/api/contact-channels/{ch_id}", headers=auth)
    assert r3.status_code == 204
    client.delete(f"/api/contacts/{c['id']}", headers=auth)


def test_channel_uniqueness(client):
    """Un mismo (type, value) no puede estar en dos contactos."""
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    import time as _time
    tg_value = f"@user{int(_time.time() * 1000) % 10_000_000}"
    c1 = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "C1"}, headers=auth).json()
    c2 = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "C2"}, headers=auth).json()
    # Asignar canal a c1
    client.post(f"/api/contacts/{c1['id']}/channels",
                json={"type": "telegram", "value": tg_value}, headers=auth)
    # Intentar el mismo canal en c2 → debe dar 409
    r = client.post(f"/api/contacts/{c2['id']}/channels",
                    json={"type": "telegram", "value": tg_value}, headers=auth)
    assert r.status_code == 409
    client.delete(f"/api/contacts/{c1['id']}", headers=auth)
    client.delete(f"/api/contacts/{c2['id']}", headers=auth)


def test_channel_validation_telegram(client):
    """Telegram rechaza valores que no sean @username ni ID numérico."""
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Val Test"}, headers=auth).json()
    r = client.post(f"/api/contacts/{c['id']}/channels",
                    json={"type": "telegram", "value": "nombre invalido"}, headers=auth)
    assert r.status_code == 400
    client.delete(f"/api/contacts/{c['id']}", headers=auth)


# ─── find_contact_by_channel (vía list) ─────────────────────────

def test_list_contacts_includes_channels(client):
    auth = get_bot_token(BOT_ID, BOT_PWD, client)
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Lista Test",
        "channels": [{"type": "telegram", "value": "@listatest"}],
    }, headers=auth).json()
    contacts = client.get(f"/api/bots/{BOT_ID}/contacts", headers=auth).json()
    found = next((x for x in contacts if x["id"] == c["id"]), None)
    assert found is not None
    assert len(found["channels"]) == 1
    client.delete(f"/api/contacts/{c['id']}", headers=auth)
