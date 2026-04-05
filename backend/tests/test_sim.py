"""Tests del simulador — olvidados antes + logging de mensajes."""

ADMIN = {"x-password": "admin"}


def test_sim_bots_loaded(client):
    """En modo sim, los bots deben estar conectados al arrancar."""
    r = client.get("/api/bots", headers=ADMIN)
    assert r.status_code == 200
    bots = r.json()
    assert len(bots) > 0


def test_sim_phones_have_ready_status(client):
    """Todos los teléfonos en modo sim deben estar en estado ready."""
    r = client.get("/api/bots", headers=ADMIN)
    bots = r.json()
    for bot in bots:
        for phone in bot.get("phones", []):
            assert phone["status"] == "ready", f"+{phone['number']} no está ready"


def test_sim_send_message(client):
    """Enviar mensaje en simulador devuelve reply cuando hay un flow activo."""
    bots = client.get("/api/bots", headers=ADMIN).json()
    bot_id = bots[0]["id"]
    number = bots[0]["phones"][0]["number"]

    # Desactivar flows por defecto para no interferir con el reply esperado
    default_flows = client.get(f"/api/empresas/{bot_id}/flows", headers=ADMIN).json()
    for f in default_flows:
        client.put(f"/api/empresas/{bot_id}/flows/{f['id']}", headers=ADMIN, json={"active": False})

    REPLY = "Respuesta automática de test"
    flow = client.post(f"/api/empresas/{bot_id}/flows", headers=ADMIN, json={
        "name": "_test_sim_send",
        "definition": {
            "nodes": [
                {"id": "__start__", "type": "start",  "position": {"x": 0, "y":   0}, "config": {}},
                {"id": "reply",     "type": "reply",  "position": {"x": 0, "y": 100}, "config": {"message": REPLY}},
                {"id": "__end__",   "type": "end",    "position": {"x": 0, "y": 200}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "__start__", "target": "reply",   "label": None},
                {"id": "e2", "source": "reply",     "target": "__end__", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }).json()
    flow_id = flow["id"]

    try:
        r = client.post(
            f"/api/sim/send/{number}",
            headers=ADMIN,
            json={"from_name": "Test", "from_phone": "5400000001", "text": "hola test"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["reply"] == REPLY
    finally:
        client.delete(f"/api/empresas/{bot_id}/flows/{flow_id}", headers=ADMIN)
        for f in default_flows:
            client.put(f"/api/empresas/{bot_id}/flows/{f['id']}", headers=ADMIN, json={"active": True})


def test_sim_send_appears_in_log(client):
    """Después de enviar, el log debe tener la línea [sim] MSG."""
    bots = client.get("/api/bots", headers=ADMIN).json()
    number = bots[0]["phones"][0]["number"]

    client.post(
        f"/api/sim/send/{number}",
        headers=ADMIN,
        json={"from_name": "LogTest", "from_phone": "5400000002", "text": "mensaje log check"},
    )

    logs = client.get("/api/logs/latest?source=backend&lines=50", headers=ADMIN).json()
    sim_lines = [l for l in logs["lines"] if "[sim] MSG" in l and "LogTest" in l]
    assert len(sim_lines) > 0, "El mensaje no apareció en el log del backend"


def test_sim_reply_appears_in_log(client):
    """El REPLY del bot debe quedar en el log cuando hay un flow activo."""
    bots = client.get("/api/bots", headers=ADMIN).json()
    bot_id = bots[0]["id"]
    number = bots[0]["phones"][0]["number"]

    # Desactivar flows por defecto para garantizar un reply determinista
    default_flows = client.get(f"/api/empresas/{bot_id}/flows", headers=ADMIN).json()
    for f in default_flows:
        client.put(f"/api/empresas/{bot_id}/flows/{f['id']}", headers=ADMIN, json={"active": False})

    flow = client.post(f"/api/empresas/{bot_id}/flows", headers=ADMIN, json={
        "name": "_test_sim_log",
        "definition": {
            "nodes": [
                {"id": "__start__", "type": "start",  "position": {"x": 0, "y":   0}, "config": {}},
                {"id": "reply",     "type": "reply",  "position": {"x": 0, "y": 100}, "config": {"message": "reply log test"}},
                {"id": "__end__",   "type": "end",    "position": {"x": 0, "y": 200}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "__start__", "target": "reply",   "label": None},
                {"id": "e2", "source": "reply",     "target": "__end__", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }).json()
    flow_id = flow["id"]

    try:
        client.post(
            f"/api/sim/send/{number}",
            headers=ADMIN,
            json={"from_name": "ReplyTest", "from_phone": "5400000003", "text": "reply check"},
        )
        logs = client.get("/api/logs/latest?source=backend&lines=50", headers=ADMIN).json()
        reply_lines = [l for l in logs["lines"] if "[sim] REPLY" in l and number in l]
        assert len(reply_lines) > 0, "El REPLY no apareció en el log del backend"
    finally:
        client.delete(f"/api/empresas/{bot_id}/flows/{flow_id}", headers=ADMIN)
        for f in default_flows:
            client.put(f"/api/empresas/{bot_id}/flows/{f['id']}", headers=ADMIN, json={"active": True})


def test_sim_connect_disconnect(client):
    """Connect y disconnect de un número en modo sim."""
    bots = client.get("/api/bots", headers=ADMIN).json()
    number = bots[0]["phones"][0]["number"]

    # Desconectar
    r = client.post(f"/api/sim/disconnect/{number}", headers=ADMIN)
    assert r.status_code == 200

    bots = client.get("/api/bots", headers=ADMIN).json()
    phone = next(p for b in bots for p in b["phones"] if p["number"] == number)
    assert phone["status"] != "ready"

    # Reconectar
    r = client.post(f"/api/sim/connect/{number}", headers=ADMIN)
    assert r.status_code == 200

    bots = client.get("/api/bots", headers=ADMIN).json()
    phone = next(p for b in bots for p in b["phones"] if p["number"] == number)
    assert phone["status"] == "ready"


def test_sim_messages_endpoint(client):
    """GET /api/sim/messages/{number} devuelve lista."""
    bots = client.get("/api/bots", headers=ADMIN).json()
    number = bots[0]["phones"][0]["number"]
    r = client.get(f"/api/sim/messages/{number}", headers=ADMIN)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_multi_empresa_dispatch(client):
    """Mensaje en conexión compartida se loguea bajo todas las empresas."""
    import time

    bots = client.get("/api/bots", headers=ADMIN).json()

    # Encontrar un número compartido entre ≥2 empresas
    phone_to_bots: dict[str, list[str]] = {}
    for bot in bots:
        for phone in bot.get("phones", []):
            num = phone["number"]
            phone_to_bots.setdefault(num, []).append(bot["id"])

    shared = {num: ids for num, ids in phone_to_bots.items() if len(ids) >= 2}
    assert shared, "No hay números WA compartidos entre empresas en connections.json"

    number, empresa_ids = next(iter(shared.items()))

    # Enviar mensaje simulado con identificador único
    unique_text = f"dispatch_test_{int(time.time() * 1000)}"
    r = client.post(
        f"/api/sim/send/{number}",
        headers=ADMIN,
        json={"from_name": "MultiTest", "from_phone": "5400009999", "text": unique_text},
    )
    assert r.status_code == 200

    # Verificar que el mensaje aparece en DB para cada empresa
    messages = client.get("/api/messages", headers=ADMIN).json()
    bots_logged = {m["connection_id"] for m in messages if m.get("body") == unique_text}

    for eid in empresa_ids:
        assert eid in bots_logged, (
            f"Empresa '{eid}' no recibió el mensaje (dispatch multi-empresa fallido).\n"
            f"Empresas que sí lo tienen: {bots_logged}"
        )
