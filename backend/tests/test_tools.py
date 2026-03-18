"""
Tests de la API de herramientas, validación de exclusividad y motor de resolución.
"""
import time

BOT_ID  = "bot_test"
BOT_PWD = "bot_test"
EMPRESA = {"x-empresa-pwd": BOT_PWD}

FIXED_MSG_PAYLOAD = {
    "nombre": "Bienvenida Test",
    "tipo": "fixed_message",
    "config": {"message": "Hola, te respondemos pronto"},
    "conexiones": [],
    "contactos_incluidos": [],
    "contactos_excluidos": [],
    "incluir_desconocidos": True,
    "exclusiva": False,
}


# ─── CRUD herramientas ────────────────────────────────────────────

def test_list_tools_empty(client):
    r = client.get(f"/api/empresas/{BOT_ID}/tools", headers=EMPRESA)
    assert r.status_code == 200
    # Puede haber herramientas de tests anteriores — verificamos solo el tipo
    assert isinstance(r.json(), list)


def test_create_tool(client):
    r = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=EMPRESA)
    assert r.status_code == 201
    body = r.json()
    assert body["nombre"] == "Bienvenida Test"
    assert body["tipo"] == "fixed_message"
    assert body["activa"] is True
    assert body["incluir_desconocidos"] is True
    client.delete(f"/api/tools/{body['id']}", headers=EMPRESA)


def test_get_tool(client):
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=EMPRESA).json()
    r = client.get(f"/api/tools/{t['id']}", headers=EMPRESA)
    assert r.status_code == 200
    assert r.json()["id"] == t["id"]
    client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)


def test_update_tool(client):
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=EMPRESA).json()
    r = client.put(f"/api/tools/{t['id']}", json={"nombre": "Bienvenida Editada"}, headers=EMPRESA)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Bienvenida Editada"
    client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)


def test_toggle_tool(client):
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=EMPRESA).json()
    assert t["activa"] is True
    r = client.post(f"/api/tools/{t['id']}/toggle", headers=EMPRESA)
    assert r.json()["activa"] is False
    client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)


def test_delete_tool(client):
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=EMPRESA).json()
    r = client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)
    assert r.status_code == 204
    r2 = client.get(f"/api/tools/{t['id']}", headers=EMPRESA)
    assert r2.status_code == 404


# ─── Validación de exclusividad ──────────────────────────────────

def test_validate_exclusivity_no_conflict(client):
    """Sin herramientas exclusivas previas → valid=True."""
    # Asegurar estado limpio: no hay herramientas exclusivas para el mismo bot
    r = client.post("/api/tools/validate-exclusivity", json={
        "empresa_id": BOT_ID,
        "tool_id": None,
        "conexiones": [],
        "contactos_incluidos": [],
        "incluir_desconocidos": False,
        "exclusiva": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True


def test_validate_exclusivity_with_conflict(client):
    """Crear herramienta exclusiva y luego validar otra que cubre los mismos desconocidos → conflict."""
    # Crear una herramienta exclusiva con incluir_desconocidos
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "exclusiva": True,
        "incluir_desconocidos": True,
    }, headers=EMPRESA).json()

    # Validar otra herramienta exclusiva con las mismas características
    r = client.post("/api/tools/validate-exclusivity", json={
        "empresa_id": BOT_ID,
        "tool_id": None,
        "conexiones": [],
        "contactos_incluidos": [],
        "incluir_desconocidos": True,
        "exclusiva": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert len(body["conflicts"]) > 0
    assert body["conflicts"][0]["conflicting_tool_id"] == t["id"]

    client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)


def test_validate_exclusivity_edit_self_no_conflict(client):
    """Al editar la misma herramienta exclusiva, no debe conflictuar consigo misma."""
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "exclusiva": True,
        "incluir_desconocidos": True,
    }, headers=EMPRESA).json()

    r = client.post("/api/tools/validate-exclusivity", json={
        "empresa_id": BOT_ID,
        "tool_id": t["id"],
        "conexiones": [],
        "contactos_incluidos": [],
        "incluir_desconocidos": True,
        "exclusiva": True,
    })
    assert r.status_code == 200
    assert r.json()["valid"] is True

    client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)


# ─── Motor de resolución (vía sim) ──────────────────────────────

def _uniq_phone(base="549199"):
    return f"{base}{int(time.time() * 1000) % 10_000_000:07d}"


def _get_wa_session_id(client):
    """Retorna el primer sessionId WA del BOT_ID, o None."""
    bots = client.get("/api/bots", headers={"x-password": "admin"}).json()
    bot = next((b for b in bots if b["id"] == BOT_ID), None)
    if not bot:
        return None
    phones = bot.get("phones", [])
    if not phones:
        return None
    return phones[0].get("sessionId") or phones[0].get("number")


def test_resolution_with_tool(client):
    """Con herramienta incluir_desconocidos activa, el sim debe responder con ese mensaje."""
    session_id = _get_wa_session_id(client)
    if not session_id:
        return  # Sin bots WA en phones.json, skip

    # Crear contacto para que pase el filtro de allowedContacts (usa DB)
    phone = _uniq_phone("549110")
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Sender Resolución",
        "channels": [{"type": "whatsapp", "value": phone}],
    }).json()

    # Crear herramienta con mensaje fijo (incluye a todos: lista vacía + incluir_desconocidos)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "nombre": "Tool Resolución Test",
        "config": {"message": "Respuesta automática de herramienta"},
        "incluir_desconocidos": True,
    }, headers=EMPRESA).json()

    # Enviar mensaje simulado
    r = client.post(f"/api/sim/send/{session_id}", json={
        "from_name": "Sender Resolución",
        "from_phone": phone,
        "text": "Hola",
    })
    assert r.status_code == 200

    # Verificar que la respuesta es el mensaje de la herramienta
    body = r.json()
    assert body.get("reply") == "Respuesta automática de herramienta"

    client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)
    client.delete(f"/api/contacts/{c['id']}")


def test_resolution_fallback_auto_reply(client):
    """Sin herramientas en DB activas, el sim usa auto_reply del JSON."""
    session_id = _get_wa_session_id(client)
    if not session_id:
        return

    # Crear contacto para que pase el filtro de allowedContacts
    phone2 = _uniq_phone("549120")
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Fallback Sender",
        "channels": [{"type": "whatsapp", "value": phone2}],
    }).json()

    # Desactivar todas las herramientas del bot
    tools = client.get(f"/api/empresas/{BOT_ID}/tools", headers=EMPRESA).json()
    active_ids = [t["id"] for t in tools if t["activa"]]
    for tid in active_ids:
        client.post(f"/api/tools/{tid}/toggle", headers=EMPRESA)

    r = client.post(f"/api/sim/send/{session_id}", json={
        "from_name": "Fallback Sender",
        "from_phone": phone2,
        "text": "Test fallback",
    })
    assert r.status_code == 200
    # Con herramientas desactivadas → responde con auto_reply del JSON (o None si no hay)
    assert "reply" in r.json()

    # Reactivar
    for tid in active_ids:
        client.post(f"/api/tools/{tid}/toggle", headers=EMPRESA)
    client.delete(f"/api/contacts/{c['id']}")


def test_resolution_excluded_contact_no_reply(client):
    """Contacto excluido → no recibe respuesta de esa herramienta."""
    session_id = _get_wa_session_id(client)
    if not session_id:
        return

    # Crear contacto y asignarlo como excluido
    phone3 = _uniq_phone("549130")
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Excluido Test",
        "channels": [{"type": "whatsapp", "value": phone3}],
    }).json()
    assert "id" in c, f"Error al crear contacto: {c}"

    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "nombre": "Tool Excluidos Test",
        "config": {"message": "Nunca deberías ver esto"},
        "contactos_excluidos": [c["id"]],
        "incluir_desconocidos": True,
    }, headers=EMPRESA).json()

    r = client.post(f"/api/sim/send/{session_id}", json={
        "from_name": "Excluido",
        "from_phone": phone3,
        "text": "Hola",
    })
    assert r.status_code == 200
    # El reply no debe ser el mensaje de esta herramienta (el contacto está excluido)
    assert r.json().get("reply") != "Nunca deberías ver esto"

    client.delete(f"/api/contacts/{c['id']}")
    client.delete(f"/api/tools/{t['id']}", headers=EMPRESA)
