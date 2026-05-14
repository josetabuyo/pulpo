"""
Tests del sistema de IDs jerárquicos en el .md del sumarizador.

Cubre:
1. _id_sort_key — ordering de IDs como tuplas
2. _read_entries_meta — lectura de IDs y timestamps del .md
3. _next_id — asignación de ID para nuevas entradas (append y middle insert)
4. accumulate() — el header lleva [id:N]
5. _parse_messages() — ordena por ID cuando hay IDs presentes
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from graphs.nodes.summarize import (
    _id_sort_key,
    _read_entries_meta,
    _next_id,
    accumulate,
    get_summary,
    clear_contact,
    _dedup,
    _dedup_loaded,
)


@pytest.fixture(autouse=True)
def tmp_summaries(monkeypatch, tmp_path):
    import graphs.nodes.summarize as sm
    monkeypatch.setattr(sm, "_BASE", tmp_path / "summaries")
    monkeypatch.setattr(sm, "_dedup", {})
    monkeypatch.setattr(sm, "_dedup_loaded", set())
    return tmp_path / "summaries"


# ─── _id_sort_key ─────────────────────────────────────────────────────────────

def test_id_sort_key_integer():
    assert _id_sort_key("3") == (3,)

def test_id_sort_key_fractional():
    assert _id_sort_key("6.1") == (6, 1)

def test_id_sort_key_fractional_large_k():
    assert _id_sort_key("6.11") == (6, 11)

def test_id_sort_key_ordering():
    ids = ["7", "6.2", "6", "6.1", "1"]
    sorted_ids = sorted(ids, key=_id_sort_key)
    assert sorted_ids == ["1", "6", "6.1", "6.2", "7"]

def test_id_sort_key_fractional_beats_next_integer():
    # 6.1 y 6.2 deben ir ENTRE 6 y 7
    ids = ["7", "6.2", "6.1", "6"]
    assert sorted(ids, key=_id_sort_key) == ["6", "6.1", "6.2", "7"]

def test_id_sort_key_multidigit_k():
    # 6.11 debe ir después de 6.9
    ids = ["6.11", "6.9", "6.1"]
    assert sorted(ids, key=_id_sort_key) == ["6.1", "6.9", "6.11"]

def test_id_sort_key_invalid_graceful():
    # IDs inválidos no explotan
    assert _id_sort_key("") == (0,)
    assert _id_sort_key(None) == (0,)


# ─── _read_entries_meta ───────────────────────────────────────────────────────

def test_read_entries_meta_empty_file(tmp_path):
    p = tmp_path / "chat.md"
    p.write_text("")
    result = _read_entries_meta(p)
    assert result == []

def test_read_entries_meta_no_ids(tmp_path):
    p = tmp_path / "chat.md"
    p.write_text(
        "## 2026-05-01 10:00\n**[text]** hola\n---\n"
        "## 2026-05-01 10:01\n**[text]** mundo\n---\n"
    )
    result = _read_entries_meta(p)
    assert len(result) == 2
    assert result[0]["id"] is None
    assert result[0]["ts"] == "2026-05-01 10:00"
    assert result[0]["id_auto"] == "1"
    assert result[1]["id_auto"] == "2"

def test_read_entries_meta_with_ids(tmp_path):
    p = tmp_path / "chat.md"
    p.write_text(
        "## 2026-05-01 10:00 [id:1]\n**[text]** hola\n---\n"
        "## 2026-05-01 10:01 [id:2]\n**[text]** mundo\n---\n"
    )
    result = _read_entries_meta(p)
    assert len(result) == 2
    assert result[0]["id"] == "1"
    assert result[1]["id"] == "2"

def test_read_entries_meta_mixed_ids(tmp_path):
    """Mezcla de entradas con y sin IDs (migración gradual)."""
    p = tmp_path / "chat.md"
    p.write_text(
        "## 2026-05-01 10:00\n**[text]** viejo\n---\n"
        "## 2026-05-01 10:01 [id:2]\n**[text]** nuevo\n---\n"
    )
    result = _read_entries_meta(p)
    assert result[0]["id"] is None
    assert result[0]["id_auto"] == "1"
    assert result[1]["id"] == "2"
    assert result[1]["id_auto"] == "2"

def test_read_entries_meta_fractional_id(tmp_path):
    p = tmp_path / "chat.md"
    p.write_text(
        "## 2026-05-01 10:00 [id:1]\n**[text]** a\n---\n"
        "## 2026-05-01 10:00:30 [id:1.1]\n**[text]** insertado\n---\n"
        "## 2026-05-01 10:01 [id:2]\n**[text]** b\n---\n"
    )
    result = _read_entries_meta(p)
    assert result[1]["id"] == "1.1"
    assert result[1]["id_auto"] == "1.1"


# ─── _next_id ─────────────────────────────────────────────────────────────────

def test_next_id_first_entry():
    assert _next_id("2026-05-01 10:00", []) == "1"

def test_next_id_append():
    entries = [
        {"id": "1", "id_auto": "1", "ts": "2026-05-01 10:00"},
        {"id": "2", "id_auto": "2", "ts": "2026-05-01 10:01"},
    ]
    assert _next_id("2026-05-01 10:02", entries) == "3"

def test_next_id_same_ts_as_last_appends():
    entries = [{"id": "1", "id_auto": "1", "ts": "2026-05-01 10:00"}]
    assert _next_id("2026-05-01 10:00", entries) == "2"

def test_next_id_middle_insert_basic():
    entries = [
        {"id": "1", "id_auto": "1", "ts": "2026-05-01 10:00"},
        {"id": "2", "id_auto": "2", "ts": "2026-05-01 10:02"},
    ]
    # Mensaje que va entre 1 y 2
    result = _next_id("2026-05-01 10:01", entries)
    assert result == "1.1"

def test_next_id_middle_insert_second_slot():
    entries = [
        {"id": "1", "id_auto": "1", "ts": "2026-05-01 10:00"},
        {"id": "1.1", "id_auto": "1.1", "ts": "2026-05-01 10:01"},
        {"id": "2", "id_auto": "2", "ts": "2026-05-01 10:02"},
    ]
    # Otro mensaje entre 10:00 y 10:01 → debería ser 1.2
    result = _next_id("2026-05-01 10:00:30", entries)
    assert result == "1.2"

def test_next_id_before_first():
    entries = [{"id": "1", "id_auto": "1", "ts": "2026-05-01 10:00"}]
    result = _next_id("2026-05-01 09:00", entries)
    assert result == "0.1"

def test_next_id_no_ids_backward_compat():
    """Entradas sin IDs (id=None, id_auto asignado por posición)."""
    entries = [
        {"id": None, "id_auto": "1", "ts": "2026-05-01 10:00"},
        {"id": None, "id_auto": "2", "ts": "2026-05-01 10:01"},
    ]
    assert _next_id("2026-05-01 10:02", entries) == "3"


# ─── accumulate() genera IDs ──────────────────────────────────────────────────

def test_accumulate_writes_id_in_header():
    eid, phone = "empresa_test", "111"
    accumulate(eid, phone, "Test", "text", "primer mensaje",
               timestamp=datetime(2026, 5, 1, 10, 0))
    content = get_summary(eid, phone)
    assert "[id:1]" in content

def test_accumulate_sequential_ids():
    eid, phone = "empresa_test", "222"
    accumulate(eid, phone, "Test", "text", "mensaje uno",
               timestamp=datetime(2026, 5, 1, 10, 0))
    accumulate(eid, phone, "Test", "text", "mensaje dos",
               timestamp=datetime(2026, 5, 1, 10, 1))
    accumulate(eid, phone, "Test", "text", "mensaje tres",
               timestamp=datetime(2026, 5, 1, 10, 2))
    content = get_summary(eid, phone)
    assert "[id:1]" in content
    assert "[id:2]" in content
    assert "[id:3]" in content

def test_accumulate_middle_insert_gets_fractional_id():
    eid, phone = "empresa_test", "333"
    # Dos mensajes en orden
    accumulate(eid, phone, "Test", "text", "primero",
               timestamp=datetime(2026, 5, 1, 10, 0))
    accumulate(eid, phone, "Test", "text", "tercero",
               timestamp=datetime(2026, 5, 1, 10, 2))
    # Un mensaje que va en el medio (ts entre los dos anteriores)
    accumulate(eid, phone, "Test", "text", "segundo",
               timestamp=datetime(2026, 5, 1, 10, 1))
    content = get_summary(eid, phone)
    assert "[id:1]" in content
    assert "[id:2]" in content
    assert "[id:1.1]" in content

def test_accumulate_no_duplicate_ids():
    eid, phone = "empresa_test", "444"
    accumulate(eid, phone, "Test", "text", "hola", timestamp=datetime(2026, 5, 1, 10, 0))
    accumulate(eid, phone, "Test", "text", "hola", timestamp=datetime(2026, 5, 1, 10, 0))
    content = get_summary(eid, phone)
    assert content.count("[id:") == 1  # solo un ID, el duplicado se skipea


# ─── _parse_messages con IDs — ordenamiento ───────────────────────────────────

def test_parse_messages_sorts_by_id():
    """Si el .md tiene entradas fuera de orden cronológico en el archivo,
    _parse_messages las ordena por ID."""
    from api.summarizer import _parse_messages
    md = (
        "## 2026-05-01 10:00 [id:1]\n**[text]** primero\n---\n"
        "## 2026-05-01 10:02 [id:2]\n**[text]** tercero\n---\n"
        "## 2026-05-01 10:01 [id:1.1]\n**[text]** segundo\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 3
    assert msgs[0]["content"] == "primero"
    assert msgs[1]["content"] == "segundo"
    assert msgs[2]["content"] == "tercero"

def test_parse_messages_no_ids_preserves_file_order():
    """Sin IDs, el orden del archivo se respeta (backward compat)."""
    from api.summarizer import _parse_messages
    md = (
        "## 2026-05-01 10:00\n**[text]** primero\n---\n"
        "## 2026-05-01 10:02\n**[text]** tercero\n---\n"
        "## 2026-05-01 10:01\n**[text]** segundo\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert len(msgs) == 3
    assert msgs[0]["content"] == "primero"
    assert msgs[1]["content"] == "tercero"
    assert msgs[2]["content"] == "segundo"

def test_parse_messages_id_not_leaked_in_output():
    """El campo _id interno no aparece en los dicts de salida."""
    from api.summarizer import _parse_messages
    md = "## 2026-05-01 10:00 [id:1]\n**[text]** hola\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert "_id" not in msgs[0]

def test_parse_messages_timestamp_stripped_of_id():
    """El timestamp devuelto no contiene la parte [id:N]."""
    from api.summarizer import _parse_messages
    md = "## 2026-05-01 10:00:00 [id:3]\n**[text]** hola\n---\n"
    msgs = _parse_messages(md, "eid", "phone")
    assert msgs[0]["timestamp"] == "2026-05-01T10:00:00"
    assert "id" not in msgs[0]["timestamp"]

def test_parse_messages_mixed_with_and_without_ids():
    """Si hay cualquier ID, se ordena por ID; las entradas sin ID van primero (id_auto=0)."""
    from api.summarizer import _parse_messages
    md = (
        "## 2026-05-01 10:00 [id:1]\n**[text]** con id\n---\n"
        "## 2026-05-01 10:02 [id:2]\n**[text]** con id también\n---\n"
    )
    msgs = _parse_messages(md, "eid", "phone")
    assert msgs[0]["content"] == "con id"
    assert msgs[1]["content"] == "con id también"
