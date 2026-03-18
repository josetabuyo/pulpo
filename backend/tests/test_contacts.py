"""
Tests de la API de contactos y lógica de canales.
Requiere servidor corriendo (BACKEND_PORT en .env).
"""
import time

BOT_ID  = "bot_test"
BOT_PWD = "bot_test"
EMPRESA = {"x-empresa-pwd": BOT_PWD}


def _uniq_phone(base="549100"):
    """Genera un número único basado en timestamp para evitar colisiones de UNIQUE(type,value)."""
    return f"{base}{int(time.time() * 1000) % 10_000_000:07d}"


# ─── CRUD contactos ───────────────────────────────────────────────

def test_list_contacts_empty(client):
    r = client.get(f"/api/bots/{BOT_ID}/contacts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_contact(client):
    r = client.post(f"/api/bots/{BOT_ID}/contacts",
                    json={"name": "Test Contact", "channels": []})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Test Contact"
    assert body["bot_id"] == BOT_ID
    assert isinstance(body["channels"], list)
    # Cleanup
    client.delete(f"/api/contacts/{body['id']}")


def test_create_contact_with_channels(client):
    phone = _uniq_phone()
    r = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Con Canales",
        "channels": [{"type": "whatsapp", "value": phone}],
    })
    assert r.status_code == 201
    body = r.json()
    assert len(body["channels"]) == 1
    assert body["channels"][0]["type"] == "whatsapp"
    assert body["channels"][0]["value"] == phone
    client.delete(f"/api/contacts/{body['id']}")


def test_get_contact(client):
    create = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Get Test"}).json()
    r = client.get(f"/api/contacts/{create['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == create["id"]
    client.delete(f"/api/contacts/{create['id']}")


def test_update_contact(client):
    create = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Old Name"}).json()
    r = client.put(f"/api/contacts/{create['id']}", json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    client.delete(f"/api/contacts/{create['id']}")


def test_delete_contact(client):
    create = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Delete Me"}).json()
    r = client.delete(f"/api/contacts/{create['id']}")
    assert r.status_code == 204
    r2 = client.get(f"/api/contacts/{create['id']}")
    assert r2.status_code == 404


def test_contact_not_found(client):
    r = client.get("/api/contacts/999999")
    assert r.status_code == 404


# ─── Canales ──────────────────────────────────────────────────────

def test_add_and_delete_channel(client):
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Channel Test"}).json()
    # Agregar canal
    r = client.post(f"/api/contacts/{c['id']}/channels",
                    json={"type": "telegram", "value": "@testuser"})
    assert r.status_code == 201
    ch_id = r.json()["id"]
    # Verificar que aparece en el contacto
    r2 = client.get(f"/api/contacts/{c['id']}")
    channels = r2.json()["channels"]
    assert any(ch["id"] == ch_id for ch in channels)
    # Eliminar canal
    r3 = client.delete(f"/api/contact-channels/{ch_id}")
    assert r3.status_code == 204
    client.delete(f"/api/contacts/{c['id']}")


def test_channel_uniqueness(client):
    """Un mismo (type, value) no puede estar en dos contactos."""
    phone = _uniq_phone("549111")
    c1 = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "C1"}).json()
    c2 = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "C2"}).json()
    # Asignar canal a c1
    client.post(f"/api/contacts/{c1['id']}/channels",
                json={"type": "whatsapp", "value": phone})
    # Intentar el mismo canal en c2 → debe dar 409
    r = client.post(f"/api/contacts/{c2['id']}/channels",
                    json={"type": "whatsapp", "value": phone})
    assert r.status_code == 409
    client.delete(f"/api/contacts/{c1['id']}")
    client.delete(f"/api/contacts/{c2['id']}")


def test_channel_validation_whatsapp(client):
    """WhatsApp solo acepta números."""
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={"name": "Val Test"}).json()
    r = client.post(f"/api/contacts/{c['id']}/channels",
                    json={"type": "whatsapp", "value": "+5491100000001"})
    assert r.status_code == 400
    client.delete(f"/api/contacts/{c['id']}")


# ─── find_contact_by_channel (vía list) ─────────────────────────

def test_list_contacts_includes_channels(client):
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Lista Test",
        "channels": [{"type": "whatsapp", "value": _uniq_phone("549112")}],
    }).json()
    contacts = client.get(f"/api/bots/{BOT_ID}/contacts").json()
    found = next((x for x in contacts if x["id"] == c["id"]), None)
    assert found is not None
    assert len(found["channels"]) == 1
    client.delete(f"/api/contacts/{c['id']}")
