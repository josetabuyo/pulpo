"""Tests de la herramienta sumarizadora."""
import sys
import os
from pathlib import Path
from datetime import datetime

# Agregar el directorio backend al sys.path para imports directos
sys.path.insert(0, str(Path(__file__).parent.parent))

ADMIN = {"x-password": os.getenv("ADMIN_PASSWORD", "admin")}


# ─── Tests unitarios del módulo summarizer ───────────────────────

def test_accumulate_crea_archivo(tmp_path, monkeypatch):
    """accumulate() crea el archivo .md si no existe."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    s.accumulate("empresa1", "5491100001", "Juan", "texto", "Hola mundo")

    p = tmp_path / "empresa1" / "5491100001.md"
    assert p.exists()
    content = p.read_text()
    assert "**[texto]**" in content
    assert "Hola mundo" in content


def test_accumulate_hace_append(tmp_path, monkeypatch):
    """Varios accumulate() dan lugar a varias entradas en el mismo .md."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    s.accumulate("e1", "5491100002", "Ana", "texto", "Primer mensaje")
    s.accumulate("e1", "5491100002", "Ana", "texto", "Segundo mensaje")
    s.accumulate("e1", "5491100002", "Ana", "texto", "Tercer mensaje")

    content = (tmp_path / "e1" / "5491100002.md").read_text()
    assert content.count("---") == 3
    assert "Primer mensaje" in content
    assert "Segundo mensaje" in content
    assert "Tercer mensaje" in content


def test_accumulate_formato_correcto(tmp_path, monkeypatch):
    """El formato de cada entrada es ## fecha\n**[tipo]** contenido\n---"""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    ts = datetime(2026, 3, 19, 14, 32)
    s.accumulate("e1", "5491100003", "Bot", "audio", "transcripción de audio", timestamp=ts)

    content = (tmp_path / "e1" / "5491100003.md").read_text()
    assert "## 2026-03-19 14:32\n" in content
    assert "**[audio]** transcripción de audio\n" in content
    assert "---\n" in content


def test_get_summary_devuelve_contenido(tmp_path, monkeypatch):
    """get_summary() retorna el texto del .md."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    s.accumulate("e1", "5491100004", "Pedro", "texto", "test get")
    result = s.get_summary("e1", "5491100004")

    assert result is not None
    assert "test get" in result


def test_get_summary_none_si_no_existe(tmp_path, monkeypatch):
    """get_summary() retorna None si no hay archivo."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    result = s.get_summary("empresa_inexistente", "9999999")
    assert result is None


def test_list_contacts(tmp_path, monkeypatch):
    """list_contacts() devuelve los teléfonos con resumen."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    s.accumulate("e2", "111", "A", "texto", "x")
    s.accumulate("e2", "222", "B", "texto", "y")

    phones = s.list_contacts("e2")
    assert set(phones) == {"111", "222"}


def test_list_contacts_empresa_sin_datos(tmp_path, monkeypatch):
    """list_contacts() devuelve lista vacía si no hay datos."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    assert s.list_contacts("empresa_vacia") == []


# ─── Tests de integración vía API ────────────────────────────────

BOT_ID  = "bot_test"
BOT_PWD = "bot_test"


def _get_empresa_token(client) -> dict:
    r = client.post("/api/empresa/login", json={"bot_id": BOT_ID, "password": BOT_PWD})
    if r.status_code != 200:
        return {}
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_summarizer_endpoint_lista_vacia(client):
    """GET /api/summarizer/{empresa_id} devuelve lista (puede estar vacía)."""
    token = _get_empresa_token(client)
    if not token:
        return
    r = client.get(f"/api/summarizer/{BOT_ID}", headers=token)
    assert r.status_code == 200
    assert "contacts" in r.json()


def test_summarizer_endpoint_404_sin_resumen(client):
    """GET /api/summarizer/{empresa_id}/telefono_inexistente → 404."""
    token = _get_empresa_token(client)
    if not token:
        return
    r = client.get(f"/api/summarizer/{BOT_ID}/9999999999", headers=token)
    assert r.status_code == 404
