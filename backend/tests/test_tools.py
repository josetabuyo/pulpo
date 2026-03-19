"""
Tests de la API de herramientas, validación de exclusividad y motor de resolución.
"""
import time
from conftest import get_empresa_token

BOT_ID  = "bot_test"
BOT_PWD = "bot_test"

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
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    r = client.get(f"/api/empresas/{BOT_ID}/tools", headers=auth)
    assert r.status_code == 200
    # Puede haber herramientas de tests anteriores — verificamos solo el tipo
    assert isinstance(r.json(), list)


def test_create_tool(client):
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    r = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["nombre"] == "Bienvenida Test"
    assert body["tipo"] == "fixed_message"
    assert body["activa"] is True
    assert body["incluir_desconocidos"] is True
    client.delete(f"/api/tools/{body['id']}", headers=auth)


def test_get_tool(client):
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=auth).json()
    r = client.get(f"/api/tools/{t['id']}", headers=auth)
    assert r.status_code == 200
    assert r.json()["id"] == t["id"]
    client.delete(f"/api/tools/{t['id']}", headers=auth)


def test_update_tool(client):
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=auth).json()
    r = client.put(f"/api/tools/{t['id']}", json={"nombre": "Bienvenida Editada"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Bienvenida Editada"
    client.delete(f"/api/tools/{t['id']}", headers=auth)


def test_toggle_tool(client):
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=auth).json()
    assert t["activa"] is True
    r = client.post(f"/api/tools/{t['id']}/toggle", headers=auth)
    assert r.json()["activa"] is False
    client.delete(f"/api/tools/{t['id']}", headers=auth)


def test_delete_tool(client):
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json=FIXED_MSG_PAYLOAD, headers=auth).json()
    r = client.delete(f"/api/tools/{t['id']}", headers=auth)
    assert r.status_code == 204
    r2 = client.get(f"/api/tools/{t['id']}", headers=auth)
    assert r2.status_code == 404


# ─── Validación de exclusividad ──────────────────────────────────

def test_validate_exclusivity_no_conflict(client):
    """Sin herramientas exclusivas previas → valid=True."""
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
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "exclusiva": True,
        "incluir_desconocidos": True,
    }, headers=auth).json()

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

    client.delete(f"/api/tools/{t['id']}", headers=auth)


def test_validate_exclusivity_edit_self_no_conflict(client):
    """Al editar la misma herramienta exclusiva, no debe conflictuar consigo misma."""
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "exclusiva": True,
        "incluir_desconocidos": True,
    }, headers=auth).json()

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

    client.delete(f"/api/tools/{t['id']}", headers=auth)


# ─── Motor de resolución (vía sim) ──────────────────────────────

def _uniq_phone(base="549199"):
    return f"{base}{int(time.time() * 1000) % 10_000_000:07d}"


def _get_exclusive_session_id(client, bot_id: str = BOT_ID):
    """
    Retorna el primer sessionId WA que pertenece EXCLUSIVAMENTE a bot_id
    (no compartido con otras empresas). Retorna None si no existe.
    En un setup multi-empresa con phones compartidos, esto puede no existir
    para ciertos bots; en ese caso los tests de resolución se saltean.
    """
    bots = client.get("/api/bots", headers={"x-password": "admin"}).json()
    phone_owners: dict[str, list[str]] = {}
    for bot in bots:
        for phone in bot.get("phones", []):
            num = phone["number"]
            phone_owners.setdefault(num, []).append(bot["id"])

    target_bot = next((b for b in bots if b["id"] == bot_id), None)
    if not target_bot:
        return None

    for phone in target_bot.get("phones", []):
        num = phone["number"]
        if len(phone_owners.get(num, [])) == 1:
            return phone.get("sessionId") or phone.get("number")
    return None


def test_resolution_with_tool(client):
    """Con herramienta incluir_desconocidos activa, el sim debe responder con ese mensaje."""
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    session_id = _get_exclusive_session_id(client)
    if not session_id:
        return  # Sin bots WA en phones.json, skip

    # Crear contacto para el test
    phone = _uniq_phone("549110")
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Sender Resolución",
        "channels": [{"type": "whatsapp", "value": phone}],
    }, headers=auth).json()

    # Crear herramienta con mensaje fijo (incluye a todos: lista vacía + incluir_desconocidos)
    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "nombre": "Tool Resolución Test",
        "config": {"message": "Respuesta automática de herramienta"},
        "incluir_desconocidos": True,
    }, headers=auth).json()

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

    client.delete(f"/api/tools/{t['id']}", headers=auth)
    client.delete(f"/api/contacts/{c['id']}", headers=auth)


def test_resolution_fallback_auto_reply(client):
    """Sin herramientas en DB activas, el sim usa auto_reply del JSON."""
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    session_id = _get_exclusive_session_id(client)
    if not session_id:
        return

    # Desactivar todas las herramientas del bot
    tools = client.get(f"/api/empresas/{BOT_ID}/tools", headers=auth).json()
    active_ids = [t["id"] for t in tools if t["activa"]]
    for tid in active_ids:
        client.post(f"/api/tools/{tid}/toggle", headers=auth)

    r = client.post(f"/api/sim/send/{session_id}", json={
        "from_name": "Fallback Sender",
        "from_phone": _uniq_phone("549120"),
        "text": "Test fallback",
    })
    assert r.status_code == 200
    # Con herramientas desactivadas → responde con auto_reply del JSON (o None si no hay)
    assert "reply" in r.json()

    # Reactivar
    for tid in active_ids:
        client.post(f"/api/tools/{tid}/toggle", headers=auth)


def test_resolution_excluded_contact_no_reply(client):
    """Contacto excluido → no recibe respuesta de esa herramienta."""
    auth = get_empresa_token(BOT_ID, BOT_PWD, client)
    session_id = _get_exclusive_session_id(client)
    if not session_id:
        return

    # Crear contacto y asignarlo como excluido
    phone3 = _uniq_phone("549130")
    c = client.post(f"/api/bots/{BOT_ID}/contacts", json={
        "name": "Excluido Test",
        "channels": [{"type": "whatsapp", "value": phone3}],
    }, headers=auth).json()
    assert "id" in c, f"Error al crear contacto: {c}"

    t = client.post(f"/api/empresas/{BOT_ID}/tools", json={
        **FIXED_MSG_PAYLOAD,
        "nombre": "Tool Excluidos Test",
        "config": {"message": "Nunca deberías ver esto"},
        "contactos_excluidos": [c["id"]],
        "incluir_desconocidos": True,
    }, headers=auth).json()

    r = client.post(f"/api/sim/send/{session_id}", json={
        "from_name": "Excluido",
        "from_phone": phone3,
        "text": "Hola",
    })
    assert r.status_code == 200
    # El reply no debe ser el mensaje de esta herramienta (el contacto está excluido)
    assert r.json().get("reply") != "Nunca deberías ver esto"

    client.delete(f"/api/contacts/{c['id']}", headers=auth)
    client.delete(f"/api/tools/{t['id']}", headers=auth)
