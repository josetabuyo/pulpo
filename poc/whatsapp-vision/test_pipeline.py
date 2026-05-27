"""
Tests unitarios del pipeline de visión WA.

Cubre las funciones puras que no requieren browser ni imágenes reales:
  - classify_msg_type
  - _is_waveform_garbage
  - _extract_timestamp
  - _find_play_button  (con imágenes sintéticas)

Correr:
  cd poc-whatsapp-vision
  source .venv/bin/activate
  pytest test_pipeline.py -v
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from importlib import import_module
pipeline = import_module("04_full_pipeline")

classify_msg_type  = pipeline.classify_msg_type
_is_waveform_garbage = pipeline._is_waveform_garbage
_extract_timestamp = pipeline._extract_timestamp
_find_play_button  = pipeline._find_play_button


# ── classify_msg_type ─────────────────────────────────────────────────────────

def _blocks(*texts):
    return [{"text": t} for t in texts]

class TestClassifyMsgType:
    def test_plain_text(self):
        assert classify_msg_type("Hola cómo estás?", _blocks("Hola cómo estás?")) == "text"

    def test_audio_by_duration(self):
        assert classify_msg_type("0:21 7:15 p. m.", _blocks("0:21", "7:15 p. m.")) == "audio"

    def test_audio_duration_not_confused_with_time(self):
        # "7:15 p. m." alone should NOT be treated as audio duration
        assert classify_msg_type("Nos vemos a las 7:15 p. m.", _blocks("Nos vemos a las 7:15 p. m.")) == "text"

    def test_audio_by_waveform_garbage(self):
        assert classify_msg_type("", _blocks("||00||0|1|0||10||")) == "audio"

    def test_file_by_extension(self):
        assert classify_msg_type("presupuesto.xlsx 48 kB", _blocks("presupuesto.xlsx", "48 kB")) == "file"

    def test_file_by_size(self):
        assert classify_msg_type("reporte.pdf 1.2 MB", _blocks("reporte.pdf", "1.2 MB")) == "file"

    def test_file_takes_priority_over_audio(self):
        # Has both a duration (0:31) and a file extension — file wins
        assert classify_msg_type("grabacion.mp4 2.5 MB", _blocks("grabacion.mp4", "2.5 MB")) == "file"

    def test_media_empty_text(self):
        assert classify_msg_type("", _blocks()) == "media"

    def test_media_blank_blocks(self):
        assert classify_msg_type("  ", _blocks("  ")) == "media"

    def test_multiline_text(self):
        result = classify_msg_type(
            "si, te decía si querías subir la página",
            _blocks("si, te decía si querías subir la página", "7:17 p. m."),
        )
        assert result == "text"


# ── _is_waveform_garbage ──────────────────────────────────────────────────────

class TestIsWaveformGarbage:
    def test_waveform_noise(self):
        assert _is_waveform_garbage("||0||0|019 0") is True

    def test_waveform_pipe_heavy(self):
        assert _is_waveform_garbage("|•01-[]lL|•01") is True

    def test_normal_text(self):
        assert _is_waveform_garbage("Hola cómo estás?") is False

    def test_too_short(self):
        assert _is_waveform_garbage("|0|") is False  # len < 5

    def test_mixed_but_below_threshold(self):
        # "hola|" → 1 noise / 5 total = 0.20 < 0.45
        assert _is_waveform_garbage("hola|") is False


# ── _extract_timestamp ────────────────────────────────────────────────────────

class TestExtractTimestamp:
    def test_standalone_block(self):
        blocks = [{"text": "Hola"}, {"text": "7:15 p. m."}]
        assert _extract_timestamp(blocks) == "7:15 p. m."

    def test_embedded_at_end(self):
        blocks = [{"text": "Que haces capo??!! 7:29 p. m."}]
        result = _extract_timestamp(blocks)
        assert result is not None
        assert "7:29" in result

    def test_am_time(self):
        blocks = [{"text": "10:03 a. m."}]
        assert _extract_timestamp(blocks) == "10:03 a. m."

    def test_no_timestamp(self):
        blocks = [{"text": "Hola"}, {"text": "cómo estás"}]
        assert _extract_timestamp(blocks) is None

    def test_duration_not_matched_as_timestamp(self):
        # "0:21" is an audio duration, NOT a timestamp (no am/pm)
        blocks = [{"text": "0:21"}]
        assert _extract_timestamp(blocks) is None

    def test_prefers_standalone_over_embedded(self):
        # Standalone "7:17 p. m." should be returned, not the embedded one
        blocks = [
            {"text": "queres que hablemos por telefono? 7:17 p. m."},
            {"text": "7:17 p. m."},
        ]
        result = _extract_timestamp(blocks)
        assert result == "7:17 p. m."


# ── _find_play_button ─────────────────────────────────────────────────────────

def _make_audio_bubble(w: int, h: int, sender: str) -> Image.Image:
    """Imagen sintética de burbuja de audio.

    'other': fondo claro, círculo oscuro ▶ en x≈15, barras de onda en x≈40-w
    'me':    fondo claro, avatar oscuro en x=0..h, círculo ▶ en x≈h+15
    """
    arr = np.full((h, w), 220, dtype=np.uint8)  # fondo gris claro

    if sender == "other":
        # ▶ button: círculo oscuro de radio 8 centrado en (15, h//2)
        cx, cy, r = 15, h // 2, 8
        for y in range(h):
            for x in range(w):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2:
                    arr[y, x] = 40  # oscuro
        # waveform: barras oscuras en x=40..w-10
        for x in range(40, w - 10, 6):
            bar_h = np.random.randint(4, h - 10)
            y_off = (h - bar_h) // 2
            arr[y_off:y_off + bar_h, x:x + 3] = 80

    else:  # "me"
        # avatar: bloque oscuro en x=0..int(h*0.6); la ventana de búsqueda
        # arranca en int(h*0.75) así que no hay solapamiento con el ▶
        arr[:, 0:int(h * 0.6)] = 60
        # ▶ button: círculo en x≈int(h*0.75)+15
        cx, cy, r = int(h * 0.75) + 15, h // 2, 8
        for y in range(h):
            for x in range(w):
                if 0 <= x < w and (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2:
                    arr[y, x] = 40
        # waveform: barras en x después del ▶
        for x in range(int(h * 0.75) + 35, w - 10, 6):
            bar_h = np.random.randint(4, h - 10)
            y_off = (h - bar_h) // 2
            arr[y_off:y_off + bar_h, x:x + 3] = 80

    return Image.fromarray(arr, mode="L")


class TestFindPlayButton:
    def test_other_x_near_left_edge(self):
        # ▶ en x≈15 — debe detectar algo en x < 30 (no en la barra de onda)
        img = _make_audio_bubble(300, 60, "other")
        rx, ry = _find_play_button(img, "other")
        assert rx < 30, f"x={rx} demasiado a la derecha para 'other' (esperado <30)"

    def test_other_y_centered(self):
        img = _make_audio_bubble(300, 60, "other")
        _, ry = _find_play_button(img, "other")
        assert 15 < ry < 45, f"y={ry} fuera del rango central para 'other'"

    def test_me_x_past_avatar(self):
        h = 60
        img = _make_audio_bubble(300, h, "me")
        rx, _ = _find_play_button(img, "me")
        # La búsqueda arranca en int(h*0.75)=45; ▶ está en ≈int(h*0.75)+15
        assert rx > int(h * 0.7), f"x={rx} dentro del avatar (esperado >{int(h * 0.7)})"

    def test_fallback_no_dark_pixels(self):
        # Imagen completamente plana — debe retornar sin error (fallback al centro)
        img = Image.fromarray(np.full((60, 300), 200, dtype=np.uint8), mode="L")
        rx, ry = _find_play_button(img, "other")
        assert isinstance(rx, int) and isinstance(ry, int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
