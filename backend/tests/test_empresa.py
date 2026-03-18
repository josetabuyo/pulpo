"""Tests del portal de empresa."""

ADMIN = {"x-password": "admin"}


def _get_first_bot(client):
    """Devuelve (bot_id, password) del primer bot en phones.json."""
    bots = client.get("/api/bots", headers=ADMIN).json()
    assert len(bots) > 0, "No hay bots configurados"
    bot = bots[0]
    # La password la obtenemos autenticándonos con la del bot directamente.
    # Como no la exponemos por API, usamos la conocida del bot de prueba.
    return bot["id"], bot


# ─── Auth ────────────────────────────────────────────────────────

def test_empresa_auth_wrong_password(client):
    r = client.post("/api/empresa/auth", json={"password": "clave_incorrecta_xyz"})
    assert r.status_code == 401


def test_empresa_auth_missing_body(client):
    r = client.post("/api/empresa/auth", json={})
    assert r.status_code == 422


# ─── Endpoints con auth válida (usa la password de test del bot_test) ──

BOT_ID  = "bot_test"
BOT_PWD = "bot_test"
EMPRESA = {"x-empresa-pwd": BOT_PWD}


def test_empresa_auth_ok(client):
    r = client.post("/api/empresa/auth", json={"password": BOT_PWD})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["bot_id"] == BOT_ID
    assert isinstance(body["bot_name"], str)


def test_empresa_get_ok(client):
    r = client.get(f"/api/empresa/{BOT_ID}", headers=EMPRESA)
    assert r.status_code == 200
    body = r.json()
    assert body["bot_id"] == BOT_ID
    assert isinstance(body["bot_name"], str)
    assert isinstance(body["connections"], list)
    assert isinstance(body["autoReplyMessage"], str)


def test_empresa_get_connections_structure(client):
    r = client.get(f"/api/empresa/{BOT_ID}", headers=EMPRESA)
    conns = r.json()["connections"]
    assert len(conns) > 0
    for c in conns:
        assert "id" in c
        assert c["type"] in ("whatsapp", "telegram")
        assert "status" in c
        assert "autoReplyMessage" in c


def test_empresa_get_wrong_auth(client):
    r = client.get(f"/api/empresa/{BOT_ID}", headers={"x-empresa-pwd": "mala_clave"})
    assert r.status_code == 401


def test_empresa_get_wrong_bot_id(client):
    """Password correcta pero bot_id que no corresponde → 401."""
    r = client.get("/api/empresa/otro_bot_id", headers=EMPRESA)
    assert r.status_code == 401


def test_empresa_get_no_auth(client):
    r = client.get(f"/api/empresa/{BOT_ID}")
    assert r.status_code == 422


def test_empresa_put_tools_ok(client):
    original = client.get(f"/api/empresa/{BOT_ID}", headers=EMPRESA).json()["autoReplyMessage"]

    new_msg = "Mensaje de prueba automatizado"
    r = client.put(f"/api/empresa/{BOT_ID}/tools", json={"autoReplyMessage": new_msg}, headers=EMPRESA)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Verificar que se guardó
    updated = client.get(f"/api/empresa/{BOT_ID}", headers=EMPRESA).json()["autoReplyMessage"]
    assert updated == new_msg

    # Restaurar
    client.put(f"/api/empresa/{BOT_ID}/tools", json={"autoReplyMessage": original}, headers=EMPRESA)


def test_empresa_put_tools_wrong_auth(client):
    r = client.put(f"/api/empresa/{BOT_ID}/tools",
                   json={"autoReplyMessage": "algo"},
                   headers={"x-empresa-pwd": "mala"})
    assert r.status_code == 401


def test_empresa_connect_sim(client):
    """En modo sim, connect devuelve status ready inmediatamente."""
    conns = client.get(f"/api/empresa/{BOT_ID}", headers=EMPRESA).json()["connections"]
    wa_conns = [c for c in conns if c["type"] == "whatsapp"]
    if not wa_conns:
        return  # no hay WA en este bot de prueba, skip
    number = wa_conns[0]["id"]

    r = client.post(f"/api/empresa/{BOT_ID}/connect/{number}", headers=EMPRESA)
    assert r.status_code == 200
    assert r.json()["sessionId"] == number


def test_empresa_disconnect_sim(client):
    """Disconnect en modo sim → ok. Reconecta al final para no dejar estado sucio."""
    conns = client.get(f"/api/empresa/{BOT_ID}", headers=EMPRESA).json()["connections"]
    wa_conns = [c for c in conns if c["type"] == "whatsapp"]
    if not wa_conns:
        return
    number = wa_conns[0]["id"]

    r = client.post(f"/api/empresa/{BOT_ID}/disconnect/{number}", headers=EMPRESA)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Restaurar estado para no romper tests posteriores
    client.post(f"/api/empresa/{BOT_ID}/connect/{number}", headers=EMPRESA)
