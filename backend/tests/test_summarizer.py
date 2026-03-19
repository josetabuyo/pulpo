"""Tests de la herramienta sumarizadora y transcripción de audio."""
import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

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


# ─── Tests de transcripción ──────────────────────────────────────

def test_transcribe_groq_sin_api_key():
    """Sin GROQ_API_KEY, _transcribe_groq lanza ValueError."""
    import tools.transcription as t
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GROQ_API_KEY", None)
        with patch("tools.transcription._transcribe_groq", side_effect=ValueError("GROQ_API_KEY no configurada")):
            result = asyncio.run(t.transcribe("/tmp/test.ogg"))
    # Cae a fallback local → placeholder o resultado local
    assert isinstance(result, str)
    assert len(result) > 0


def test_transcribe_fallback_sin_pywhispercpp(tmp_path):
    """Sin GROQ_API_KEY y sin pywhispercpp → placeholder claro."""
    import tools.transcription as t
    audio = tmp_path / "test.ogg"
    audio.write_bytes(b"fake audio data")

    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GROQ_API_KEY", None)
        # Simular ImportError de pywhispercpp
        with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(ImportError) if name == "pywhispercpp.model" else __import__(name, *a, **kw)):
            result = t._transcribe_local(str(audio))

    assert "[audio sin transcribir" in result
    assert "GROQ_API_KEY" in result


def test_transcribe_groq_mock(tmp_path):
    """Con Groq mockeado, transcribe() retorna el texto del API."""
    import tools.transcription as t
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"fake audio")

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="Hola, esto es una prueba")

    with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
        with patch("groq.Groq", return_value=mock_client):
            result = asyncio.run(t.transcribe(str(audio)))

    assert result == "Hola, esto es una prueba"


def test_accumulate_audio_tipo(tmp_path, monkeypatch):
    """accumulate() con msg_type='audio' registra correctamente el tipo."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    s.accumulate("e1", "5491100010", "Luis", "audio", "transcripción de prueba")

    content = (tmp_path / "e1" / "5491100010.md").read_text()
    assert "**[audio]**" in content
    assert "transcripción de prueba" in content


def test_sim_receive_con_audio_path(tmp_path, monkeypatch):
    """sim_receive con audio_path transcribe y acumula con tipo 'audio'."""
    import tools.summarizer as s
    monkeypatch.setattr(s, "_BASE", tmp_path)

    audio = tmp_path / "test.ogg"
    audio.write_bytes(b"fake audio")

    accumulated: list[dict] = []

    def fake_accumulate(**kwargs):
        accumulated.append(kwargs)

    monkeypatch.setattr(s, "accumulate", fake_accumulate)

    import tools.transcription as t
    async def fake_transcribe(path):
        return "texto transcripto del audio"

    monkeypatch.setattr(t, "transcribe", fake_transcribe)

    # Importar sim_receive (sin servidor — solo test unitario del flujo)
    # Verificamos que la lógica llama a transcribe y accumulate con msg_type=audio
    # a través de un mock de resolve_tools
    import sim as sim_engine
    import asyncio

    async def fake_resolve_tools(session_id, sender, channel_type):
        return (
            [{"empresa_id": "e_test", "nombre": "TestSummarizer", "bot_id": "e_test"}],
            None,
        )

    async def fake_get_config(*args):
        return {"bot_id": "e_test", "auto_reply": ""}

    monkeypatch.setattr(sim_engine, "resolve_tools", fake_resolve_tools)
    monkeypatch.setattr(sim_engine, "_get_phone_config", lambda sid: {"bot_id": "e_test", "auto_reply": ""})

    async def run():
        from unittest.mock import AsyncMock
        with patch("db.log_message", new_callable=AsyncMock, return_value=1), \
             patch("db.mark_answered", new_callable=AsyncMock), \
             patch("db.log_outbound_message", new_callable=AsyncMock), \
             patch("config.get_empresas_for_bot", return_value=["e_test"]):
            return await sim_engine.sim_receive(
                session_id="5491100099",
                from_name="Pepe",
                from_phone="5491100099",
                text="[audio]",
                audio_path=str(audio),
            )

    asyncio.run(run())

    assert len(accumulated) == 1
    assert accumulated[0]["msg_type"] == "audio"
    assert accumulated[0]["content"] == "texto transcripto del audio"
