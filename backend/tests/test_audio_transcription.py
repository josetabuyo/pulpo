"""
Tests de transcripción de audio en el flow.

Cubren dos rutas críticas:
1. TranscribeAudioNode — transcribe cuando hay attachment_path
2. SummarizeNode — guarda la transcripción real en el .md
3. _parse_messages — parsea entradas de audio del .md correctamente
"""
import sys
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from graphs.nodes.state import FlowState
from graphs.nodes.transcribe_audio import TranscribeAudioNode
from graphs.nodes.summarize import SummarizeNode, accumulate, get_summary, clear_contact


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_audio_state(message="", attachment_path=None):
    return FlowState(
        message=message,
        message_type="audio",
        empresa_id="test_empresa",
        contact_phone="5491100000",
        contact_name="Test User",
    )


# ─── TranscribeAudioNode ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transcribe_audio_node_skip_if_no_audio_type():
    """Si message_type != audio, el nodo pasa sin tocar nada."""
    state = FlowState(message="hola", message_type="text", empresa_id="e", contact_phone="1")
    result = await TranscribeAudioNode({}).run(state)
    assert result.message == "hola"


@pytest.mark.asyncio
async def test_transcribe_audio_node_skip_if_already_has_message():
    """Si ya hay transcripción real, no sobreescribir."""
    state = make_audio_state(message="ya transcripto")
    result = await TranscribeAudioNode({}).run(state)
    assert result.message == "ya transcripto"


@pytest.mark.asyncio
async def test_transcribe_audio_node_does_not_skip_placeholder():
    """Si state.message es un placeholder conocido, intenta transcribir de todas formas."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.write(b"\x00" * 100)
    tmp.close()

    state = make_audio_state(message="[audio — no disponible]")
    state.attachment_path = tmp.name

    with patch("tools.transcription.transcribe", new=AsyncMock(return_value="transcripción real")):
        result = await TranscribeAudioNode({}).run(state)

    assert result.message == "transcripción real"
    Path(tmp.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_transcribe_audio_node_does_not_skip_sin_blob_placeholder():
    """[audio — sin blob] también se reintenta."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.write(b"\x00" * 100)
    tmp.close()

    state = make_audio_state(message="[audio — sin blob]")
    state.attachment_path = tmp.name

    with patch("tools.transcription.transcribe", new=AsyncMock(return_value="texto recuperado")):
        result = await TranscribeAudioNode({}).run(state)

    assert result.message == "texto recuperado"
    Path(tmp.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_transcribe_audio_node_skip_if_no_attachment():
    """Sin attachment_path, no puede transcribir."""
    state = make_audio_state()
    result = await TranscribeAudioNode({}).run(state)
    assert result.message == ""


@pytest.mark.asyncio
async def test_transcribe_audio_node_transcribes_file():
    """Con archivo válido, llama a transcription.transcribe y pone el resultado en state.message."""
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.write(b"\x00" * 100)
    tmp.close()

    state = make_audio_state()
    state.attachment_path = tmp.name

    with patch("tools.transcription.transcribe", new=AsyncMock(return_value="hola soy la transcripción")):
        result = await TranscribeAudioNode({}).run(state)

    assert result.message == "hola soy la transcripción"
    Path(tmp.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_transcribe_audio_node_file_not_found():
    """Si el archivo no existe, pone el placeholder de archivo no encontrado."""
    state = make_audio_state()
    state.attachment_path = "/tmp/no_existe_este_archivo.ogg"
    result = await TranscribeAudioNode({}).run(state)
    assert result.message == "[audio — archivo no encontrado]"


@pytest.mark.asyncio
async def test_transcribe_audio_node_handles_transcription_error():
    """Si transcription lanza excepción, pone el placeholder de error."""
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.write(b"\x00" * 100)
    tmp.close()

    state = make_audio_state()
    state.attachment_path = tmp.name

    with patch("tools.transcription.transcribe", new=AsyncMock(side_effect=RuntimeError("API caída"))):
        result = await TranscribeAudioNode({}).run(state)

    assert result.message == "[audio — error al transcribir]"
    Path(tmp.name).unlink(missing_ok=True)


# ─── SummarizeNode ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_summaries(monkeypatch, tmp_path):
    """Redirige _BASE a un dir temporal para que los tests no toquen data/summaries real."""
    import graphs.nodes.summarize as sm
    monkeypatch.setattr(sm, "_BASE", tmp_path / "summaries")
    monkeypatch.setattr(sm, "_dedup", {})
    monkeypatch.setattr(sm, "_dedup_loaded", set())
    return tmp_path / "summaries"


@pytest.mark.asyncio
async def test_summarize_node_saves_real_transcription():
    """Cuando state.message tiene texto real, SummarizeNode lo guarda en el .md."""
    state = FlowState(
        message="esto es una transcripción real del audio",
        message_type="audio",
        empresa_id="test_empresa",
        contact_phone="5491100000",
        contact_name="Test User",
        timestamp=datetime(2026, 4, 17, 18, 15),
        from_delta_sync=True,
    )
    await SummarizeNode({}).run(state)
    content = get_summary("test_empresa", "5491100000")
    assert content is not None
    assert "esto es una transcripción real del audio" in content
    assert "**[audio]**" in content


@pytest.mark.asyncio
async def test_summarize_node_saves_audio_placeholder():
    """Un placeholder como [audio — no disponible] IGUAL debe guardarse — es información."""
    state = FlowState(
        message="[audio — no disponible]",
        message_type="audio",
        empresa_id="test_empresa",
        contact_phone="5491100000",
        contact_name="Test User",
        from_delta_sync=True,
    )
    await SummarizeNode({}).run(state)
    content = get_summary("test_empresa", "5491100000")
    # El registro debe existir para no perder información de que llegó un audio
    assert content is not None
    assert "[audio — no disponible]" in content


@pytest.mark.asyncio
async def test_summarize_node_skips_empty_message():
    """Si state.message está vacío, no guarda nada."""
    state = FlowState(
        message="",
        message_type="audio",
        empresa_id="test_empresa",
        contact_phone="5491100000",
        contact_name="Test User",
    )
    await SummarizeNode({}).run(state)
    content = get_summary("test_empresa", "5491100000")
    assert content is None


# ─── _parse_messages ──────────────────────────────────────────────────────────

def test_parse_messages_audio_with_real_transcription():
    """Una entrada de audio con texto real parsea correctamente."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 18:15\n**[audio]** hola mundo transcripto\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "audio"
    assert m["transcription"] == "hola mundo transcripto"


def test_parse_messages_audio_with_placeholder():
    """Una entrada con placeholder igual se parsea — el frontend puede decidir qué mostrar."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 18:15\n**[audio]** [audio — no disponible]\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "audio"
    assert m["transcription"] == "[audio — no disponible]"


def test_parse_messages_audio_with_transcripcion_prefix():
    """Formato con prefijo _transcripción:_ también parsea correctamente."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 18:15\n**[audio 1:55]** _transcripción:_ esto es lo que dijo\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "audio"
    assert m["duration"] == "1:55"
    assert m["transcription"] == "esto es lo que dijo"


# ─── _is_useful (filtro del sync) ────────────────────────────────────────────

def test_is_useful_filters_audio_duration():
    """Duraciones de audio crudas de la DB no son útiles."""
    from api.summarizer import _is_useful
    assert not _is_useful("1:55")
    assert not _is_useful("0:37")
    assert not _is_useful("12:34")


def test_is_useful_filters_typing_indicator():
    """Indicadores de typing no son útiles."""
    from api.summarizer import _is_useful
    assert not _is_useful("Fabian está grabando un audio…")
    assert not _is_useful("Alguien está grabando un audio...")


def test_is_useful_filters_audio_placeholders():
    """Placeholders de audio de la DB no son útiles."""
    from api.summarizer import _is_useful
    assert not _is_useful("[audio — no disponible]")
    assert not _is_useful("[audio — sin blob]")
    assert not _is_useful("[audio — error al transcribir]")


def test_is_useful_passes_real_text():
    """Texto real sí pasa el filtro."""
    from api.summarizer import _is_useful
    assert _is_useful("Hola, ¿cómo estás?")
    assert _is_useful("Cuando tengas el sp avísame")
    assert _is_useful("Dale")  # 4 chars, pasa


def test_is_useful_filters_skip_exact():
    """Mensajes de media sin contenido se filtran."""
    from api.summarizer import _is_useful
    assert not _is_useful("Foto")
    assert not _is_useful("GIF")
    assert not _is_useful("Video")


def test_parse_messages_mix_audio_and_text():
    """Mezcla de mensajes de audio y texto se parsea en orden."""
    from api.summarizer import _parse_messages
    md = (
        "## 2026-04-17 18:00\n**[text]** hola\n---\n"
        "## 2026-04-17 18:15\n**[audio]** transcripción del audio\n---\n"
        "## 2026-04-17 18:20\n**[text]** ok dale\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 3
    assert msgs[0]["type"] == "text"
    assert msgs[1]["type"] == "audio"
    assert msgs[2]["type"] == "text"


# ─── Reply quotes ─────────────────────────────────────────────────────────────

def test_parse_messages_reply_with_sender():
    """> ↩ [SenderName] texto citado se parsea en reply_to con el sender embebido."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 18:00\n**[text]** ok perfecto\n> ↩ [Fabian] cuándo está listo?\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["reply_to"] == "[Fabian] cuándo está listo?"


def test_parse_messages_reply_without_sender():
    """> ↩ sin sender se parsea igual, con reply_to = texto plano."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 18:00\n**[text]** sí\n> ↩ mensaje citado sin sender\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    assert msgs[0]["reply_to"] == "mensaje citado sin sender"


def test_parse_messages_no_reply():
    """Mensaje sin quote tiene reply_to = None."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 18:00\n**[text]** hola\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert msgs[0]["reply_to"] is None


def test_parse_messages_audio_with_reply():
    """Audio con reply captura transcripción y reply_to correctamente."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 18:00\n**[audio]** _transcripción:_ lo que dije\n> ↩ [Juan] pregunta original\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "audio"
    assert m["transcription"] == "lo que dije"
    assert m["reply_to"] == "[Juan] pregunta original"


# ─── Dedup audio gana sobre texto ────────────────────────────────────────────

def test_parse_messages_audio_replaces_text_with_same_content():
    """Si llega [text] primero y luego [audio] con el mismo contenido, el audio reemplaza al texto."""
    from api.summarizer import _parse_messages
    content = "esto es lo que dijo textualmente el usuario en el audio"
    md = (
        f"## 2026-04-17 08:00\n**[text]** {content}\n---\n"
        f"## 2026-04-17 08:05\n**[audio 0:45]** _transcripción:_ {content}\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    # Solo uno: el audio (más rico) reemplaza al texto
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "audio"
    assert m["transcription"] == content
    assert m["duration"] == "0:45"


def test_parse_messages_audio_wins_over_text_preserves_position():
    """El audio reemplaza al texto pero mantiene la posición en la lista."""
    from api.summarizer import _parse_messages
    content = "frase larga que llega primero como texto y luego como audio transcripto"
    md = (
        "## 2026-04-17 08:00\n**[text]** hola\n---\n"
        f"## 2026-04-17 08:01\n**[text]** {content}\n---\n"
        f"## 2026-04-17 08:05\n**[audio]** {content}\n---\n"
        "## 2026-04-17 08:10\n**[text]** adios\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    # hola + audio (en posición 2) + adios = 3 mensajes
    assert len(msgs) == 3
    assert msgs[0]["content"] == "hola"
    assert msgs[1]["type"] == "audio"
    assert msgs[2]["content"] == "adios"


def test_parse_messages_audio_does_not_duplicate_audio():
    """Si audio llega dos veces con el mismo contenido, solo se guarda uno."""
    from api.summarizer import _parse_messages
    content = "la misma transcripción exacta"
    md = (
        f"## 2026-04-17 08:00\n**[audio]** {content}\n---\n"
        f"## 2026-04-17 08:05\n**[audio]** {content}\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1


# ─── Dedup de acumulación (accumulate + _ensure_loaded) ──────────────────────

def test_accumulate_media_placeholder_not_readded_on_restart():
    """Media placeholder no se re-acumula al reiniciar (dedup solo por contenido)."""
    from graphs.nodes.summarize import accumulate, get_summary, _dedup, _dedup_loaded
    eid, phone = "emp_test", "9999"

    # Primera vez: acumular el placeholder
    accumulate(eid, phone, "Test", "audio", "[audio — sin blob]",
               timestamp=datetime(2026, 4, 17, 10, 0))
    # Simular reinicio: limpiar dedup en memoria (pero el archivo queda en disco)
    _dedup.clear()
    _dedup_loaded.clear()

    # Segunda llamada con DISTINTO timestamp (como si el bot lo re-procesara al reiniciar)
    accumulate(eid, phone, "Test", "audio", "[audio — sin blob]",
               timestamp=datetime(2026, 4, 17, 10, 5))

    content = get_summary(eid, phone)
    # Solo debe aparecer UNA vez
    assert content.count("[audio — sin blob]") == 1


def test_accumulate_real_message_not_readded_same_ts():
    """Mensaje real no se duplica si mismo ts + contenido."""
    from graphs.nodes.summarize import accumulate, get_summary
    eid, phone = "emp_test", "8888"
    ts = datetime(2026, 4, 17, 10, 0)
    accumulate(eid, phone, "Test", "text", "hola mundo", timestamp=ts)
    accumulate(eid, phone, "Test", "text", "hola mundo", timestamp=ts)
    content = get_summary(eid, phone)
    assert content.count("hola mundo") == 1


def test_ensure_loaded_hashes_block_with_reply():
    """_ensure_loaded hashea correctamente bloques con > ↩ (no duplica al re-acumular)."""
    from graphs.nodes.summarize import accumulate, get_summary, _dedup, _dedup_loaded
    eid, phone = "emp_test", "7777"
    ts = datetime(2026, 4, 17, 10, 0)
    # Primer acumulate con reply quote
    content_with_reply = "ok\n> ↩ [Fabian] mensaje citado"
    accumulate(eid, phone, "Test", "text", content_with_reply, timestamp=ts)
    # Simular reinicio
    _dedup.clear()
    _dedup_loaded.clear()
    # Mismo acumulate de nuevo (como si el bot lo reprocesara)
    accumulate(eid, phone, "Test", "text", content_with_reply, timestamp=ts)
    content = get_summary(eid, phone)
    # Debe aparecer solo una vez
    assert content.count("ok") == 1


# ─── _parse_messages: imagen ──────────────────────────────────────────────────

def test_parse_messages_image_type():
    """Mensajes de imagen se parsean como type=image."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 12:00\n**[imagen]** [imagen guardada: foto.jpg]\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "image"
    assert m["filename"] == "foto.jpg"


def test_parse_messages_image_with_reply():
    """Imagen con reply_to se parsea correctamente."""
    from api.summarizer import _parse_messages
    md = "## 2026-04-17 12:00\n**[imagen]** [imagen guardada: foto.jpg]\n> ↩ [Fabian] mensaje original\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    assert msgs[0]["reply_to"] == "[Fabian] mensaje original"


# ─── Dedup temporal UTC/local ─────────────────────────────────────────────────

def test_parse_messages_dedup_utc_local_short_text():
    """Mensajes cortos con diferencia de 3h (UTC vs local ART) se tratan como duplicado."""
    from api.summarizer import _parse_messages
    # Mismo contenido a las 20:34 (local) y 23:34 (UTC) del mismo día
    md = (
        "## 2026-04-12 20:34\n**[text]** Jose...el SP cambió\n---\n"
        "## 2026-04-12 23:34\n**[text]** Jose...el SP cambió\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1
    assert msgs[0]["timestamp"] == "2026-04-12T20:34:00"  # se queda con el primero


def test_parse_messages_dedup_temporal_no_falso_positivo():
    """El mismo texto enviado en días diferentes NO se deduplica."""
    from api.summarizer import _parse_messages
    md = (
        "## 2026-04-10 20:34\n**[text]** Dale\n---\n"
        "## 2026-04-12 20:34\n**[text]** Dale\n---\n"
        "## 2026-04-17 18:36\n**[text]** Dale\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    # Tres "Dale" en días distintos son mensajes distintos
    assert len(msgs) == 3


def test_parse_messages_dedup_temporal_dentro_de_4h():
    """Mismo texto con 3h59m de diferencia → duplicado."""
    from api.summarizer import _parse_messages
    md = (
        "## 2026-04-12 20:00\n**[text]** texto corto\n---\n"
        "## 2026-04-12 23:59\n**[text]** texto corto\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 1


def test_parse_messages_dedup_temporal_fuera_de_4h():
    """Mismo texto con 5h de diferencia → mensajes distintos (no duplicar)."""
    from api.summarizer import _parse_messages
    md = (
        "## 2026-04-12 10:00\n**[text]** texto corto\n---\n"
        "## 2026-04-12 15:01\n**[text]** texto corto\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 2
