"""
Tests de integración de /api/wavi (requieren server corriendo).

Solo se usan nombres de sesión INVÁLIDOS o lecturas: estos tests nunca
crean sesiones wavi reales ni envían mensajes.
"""
from conftest import ADMIN

INVALID_NAMES = ["../evil", "a b", "a/b", ".oculta", "x" * 100, "-empieza-con-guion"]


def test_create_session_nombre_invalido_422(client):
    for bad in INVALID_NAMES:
        r = client.post("/api/wavi/sessions", headers=ADMIN, json={"session": bad})
        assert r.status_code == 422, f"{bad!r} debería ser rechazado, dio {r.status_code}"


def test_create_session_requiere_auth(client):
    r = client.post("/api/wavi/sessions", json={"session": "cualquiera"})
    assert r.status_code in (401, 422)


def test_get_session_nombre_invalido_422(client):
    r = client.get("/api/wavi/sessions/a%20b", headers=ADMIN)
    assert r.status_code == 422


def test_delete_session_nombre_invalido_422(client):
    r = client.delete("/api/wavi/sessions/a%20b", headers=ADMIN)
    assert r.status_code == 422


def test_list_sessions_ok(client):
    # El status real consulta el CLI wavi — puede tardar varios segundos
    import httpx
    from conftest import BASE
    with httpx.Client(base_url=BASE, timeout=30) as slow_client:
        r = slow_client.get("/api/wavi/sessions", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for s in body:
        assert "session" in s
        assert "daemon_running" in s
        assert "authenticated" in s


def test_list_sessions_requiere_auth(client):
    r = client.get("/api/wavi/sessions")
    assert r.status_code in (401, 422)


def test_qr_page_requiere_password(client):
    r = client.get("/api/wavi/qr-page")
    assert r.status_code == 401
