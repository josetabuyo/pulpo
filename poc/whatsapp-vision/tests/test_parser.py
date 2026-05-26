"""
Tests para las funciones de parsing de 04_full_pipeline.py.
Cubre: classify_x, is_noise, tag_blocks, group_into_messages.
"""
import pytest

# Las funciones viven en 04_full_pipeline; conftest.py agrega el poc root al path.
from importlib import import_module
import importlib.util
from pathlib import Path

# Importar sin ejecutar el __main__
spec = importlib.util.spec_from_file_location(
    "pipeline",
    Path(__file__).parent.parent / "04_full_pipeline.py",
)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

classify_x         = pipeline.classify_x
is_noise           = pipeline.is_noise
tag_blocks         = pipeline.tag_blocks
group_into_messages = pipeline.group_into_messages
Message            = pipeline.Message
Attachment         = pipeline.Attachment


# ─── classify_x ──────────────────────────────────────────────────────────────

def test_classify_me_right_edge():
    # right_edge = 0.9 + 0.1 = 1.0 > 0.75 → "me"
    assert classify_x(0.9, 0.1) == "me"


def test_classify_me_short_line_near_right():
    # Línea corta en burbuja "me": x=0.60, w=0.20 → right_edge=0.80 > 0.75 → "me"
    assert classify_x(0.60, 0.20) == "me"


def test_classify_other_left_edge():
    # x=0.05 < 0.15 → "other"
    assert classify_x(0.05, 0.30) == "other"


def test_classify_fallback_center_me():
    # Ni left ni right edge claros → usa centro: x=0.40, w=0.25 → center=0.525 > 0.50
    assert classify_x(0.40, 0.25) == "me"


def test_classify_fallback_center_other():
    # centro: x=0.20, w=0.20 → center=0.30 ≤ 0.50
    assert classify_x(0.20, 0.20) == "other"


# ─── is_noise ────────────────────────────────────────────────────────────────

def test_noise_empty():
    assert is_noise("") is True


def test_noise_single_char():
    assert is_noise("x") is True


def test_noise_plus_sign():
    assert is_noise("+") is True


def test_noise_escribe_mensaje():
    assert is_noise("Escribe un mensaje aquí") is True


def test_noise_encriptados():
    assert is_noise("Los mensajes están encriptados") is True


def test_noise_short_no_letters():
    assert is_noise("123") is True  # len ≤ 4, sin letras


def test_noise_cyrillic():
    assert is_noise("Привет") is True  # solo cirílico


def test_not_noise_normal_text():
    assert is_noise("Hola, ¿cómo estás?") is False


def test_not_noise_file_name():
    assert is_noise("reporte_enero.xlsx") is False


# ─── tag_blocks ──────────────────────────────────────────────────────────────

def _block(text, x=0.1, y=0.1, w=0.3, h=0.02):
    return {"text": text, "x": x, "y": y, "w": w, "h": h}


def test_tag_timestamp():
    blocks = [_block("3:45 p. m.")]
    tag_blocks(blocks)
    assert blocks[0]["role"] == "timestamp"


def test_tag_audio_duration():
    blocks = [_block("1:23")]
    tag_blocks(blocks)
    assert blocks[0]["role"] == "audio_duration"


def test_tag_filename_xlsx():
    blocks = [_block("informe.xlsx")]
    tag_blocks(blocks)
    assert blocks[0]["role"] == "filename"


def test_tag_filesize_promotes_prev_to_filename():
    blocks = [_block("documento.pdf"), _block("234 kB", y=0.12)]
    tag_blocks(blocks)
    assert blocks[0]["role"] == "filename"
    assert blocks[1]["role"] == "filesize"


def test_tag_plain_text():
    blocks = [_block("Hola! ¿Cómo va todo?")]
    tag_blocks(blocks)
    assert blocks[0]["role"] == "text"


# ─── group_into_messages ─────────────────────────────────────────────────────

def _make_blocks(*items):
    """Helper: lista de (text, x, w, y) → bloque OCR."""
    blocks = []
    for text, x, w, y in items:
        blocks.append({"text": text, "x": x, "w": w, "y": y, "h": 0.02})
    return blocks


def test_group_simple_two_messages():
    blocks = _make_blocks(
        ("Hola!",         0.05, 0.30, 0.10),  # other (x < 0.15)
        ("3:00 p. m.",    0.05, 0.10, 0.11),  # timestamp for other
        ("Buenas!",       0.60, 0.30, 0.20),  # me (right_edge=0.90 > 0.75)
        ("3:01 p. m.",    0.60, 0.10, 0.21),  # timestamp for me
    )
    msgs = group_into_messages(blocks)
    assert len(msgs) == 2
    assert msgs[0].sender == "other"
    assert msgs[0].text == "Hola!"
    assert msgs[0].time == "3:00 p. m."
    assert msgs[1].sender == "me"
    assert msgs[1].text == "Buenas!"
    assert msgs[1].time == "3:01 p. m."


def test_group_multiline_same_bubble():
    # Dos líneas del mismo lado, gap pequeño → mismo mensaje
    blocks = _make_blocks(
        ("Primera línea",  0.60, 0.25, 0.10),
        ("segunda línea",  0.60, 0.25, 0.115),  # gap=0.015 < 0.020
    )
    msgs = group_into_messages(blocks)
    assert len(msgs) == 1
    assert "Primera línea" in msgs[0].text
    assert "segunda línea" in msgs[0].text


def test_group_filters_noise():
    blocks = _make_blocks(
        ("Escribe un mensaje", 0.05, 0.50, 0.95),  # noise → ignorado
        ("Hola",              0.05, 0.20, 0.10),
    )
    msgs = group_into_messages(blocks)
    assert len(msgs) == 1
    assert msgs[0].text == "Hola"


def test_group_with_audio():
    blocks = _make_blocks(
        ("0:38",  0.60, 0.10, 0.10),   # audio_duration
    )
    msgs = group_into_messages(blocks)
    assert len(msgs) == 1
    assert len(msgs[0].attachments) == 1
    assert msgs[0].attachments[0].kind == "audio"
