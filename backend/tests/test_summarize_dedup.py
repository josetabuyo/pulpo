"""
Tests de deduplicación de accumulate() y parsing de _parse_messages().

Heredados de test_import_retry.py (el feature import-wa-history fue eliminado
junto con el soporte WhatsApp 2026-06-08; estos tests cubren lógica que sigue viva
en graphs/nodes/summarize.py y api/summarizer.py).

Son unitarios puros — no requieren server corriendo.
"""
import textwrap

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from graphs.nodes.summarize import accumulate, invalidate_dedup, _dedup, _dedup_loaded, _iter_entry_hashes
from api.summarizer import _parse_messages


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_dedup(empresa_id: str, contact_phone: str):
    key = (empresa_id, contact_phone)
    _dedup_loaded.discard(key)
    _dedup.pop(key, None)


# ── Tests de enriquecimiento de placeholders ──────────────────────────────────

def test_accumulate_no_duplicates_on_second_run(tmp_path):
    """Mismo mensaje llamado dos veces → solo una entrada en el .md."""
    import os
    os.environ.setdefault("DATA_DIR", str(tmp_path))
    # Parchamos _BASE para que use tmp_path
    from graphs.nodes import summarize as _sum_mod
    orig_base = _sum_mod._BASE
    _sum_mod._BASE = tmp_path
    try:
        eid, cp = "emp1", "contacto1"
        _reset_dedup(eid, cp)
        from datetime import datetime
        ts = datetime(2026, 5, 4, 14, 23)
        accumulate(eid, cp, "Contacto", "text", "Contacto: Gracias", timestamp=ts)
        accumulate(eid, cp, "Contacto", "text", "Contacto: Gracias", timestamp=ts)
        md = _sum_mod._path(eid, cp)
        count = md.read_text().count("---\n")
        assert count == 1, f"Esperaba 1 entrada, hubo {count}"
    finally:
        _sum_mod._BASE = orig_base
        _reset_dedup(eid, cp)


def test_accumulate_enriches_failed_audio(tmp_path):
    """Audio con [audio — sin blob] se reemplaza al llegar la transcripción real."""
    from graphs.nodes import summarize as _sum_mod
    orig_base = _sum_mod._BASE
    _sum_mod._BASE = tmp_path
    try:
        eid, cp = "emp2", "contacto2"
        _reset_dedup(eid, cp)
        from datetime import datetime
        ts = datetime(2026, 5, 4, 14, 36)
        # Primera vez: placeholder
        accumulate(eid, cp, "Contacto", "audio", "Andrés: [audio — sin blob]", timestamp=ts)
        md = _sum_mod._path(eid, cp)
        assert "[audio — sin blob]" in md.read_text()
        # Segunda vez: transcripción real
        accumulate(eid, cp, "Contacto", "audio", "Andrés: Bueno, te mando los datos", timestamp=ts)
        text = md.read_text()
        assert "Bueno, te mando los datos" in text, "Transcripción real no encontrada"
        assert "[audio — sin blob]" not in text, "Placeholder debería haber sido reemplazado"
        assert text.count("---\n") == 1, "No debería haber duplicados"
    finally:
        _sum_mod._BASE = orig_base
        _reset_dedup(eid, cp)


def test_accumulate_keeps_ok_audio_unchanged(tmp_path):
    """Audio ya con transcripción real no se modifica en la segunda pasada."""
    from graphs.nodes import summarize as _sum_mod
    orig_base = _sum_mod._BASE
    _sum_mod._BASE = tmp_path
    try:
        eid, cp = "emp3", "contacto3"
        _reset_dedup(eid, cp)
        from datetime import datetime
        ts = datetime(2026, 5, 4, 14, 22)
        accumulate(eid, cp, "Contacto", "audio", "Andrés: Primera transcripción", timestamp=ts)
        accumulate(eid, cp, "Contacto", "audio", "Andrés: Primera transcripción", timestamp=ts)
        md = _sum_mod._path(eid, cp)
        assert md.read_text().count("---\n") == 1
        assert "Primera transcripción" in md.read_text()
    finally:
        _sum_mod._BASE = orig_base
        _reset_dedup(eid, cp)


def test_accumulate_no_duplica_con_y_sin_sender(tmp_path):
    """Si el mismo mensaje llega sin sender y luego con sender, debe haber solo 1 entrada."""
    from graphs.nodes import summarize as m
    orig = m._BASE
    m._BASE = tmp_path
    try:
        eid, cp = "e", "c"
        _reset_dedup(eid, cp)
        from datetime import datetime
        ts = datetime(2026, 5, 13, 14, 20)
        accumulate(eid, cp, "Contacto", "text", "Hola José, confirmada mi visita", timestamp=ts)
        accumulate(eid, cp, "Contacto", "text", "Contacto: Hola José, confirmada mi visita", timestamp=ts)
        assert m._path(eid, cp).read_text().count("---\n") == 1, "Mismo mensaje con/sin sender debe deduplicarse"
    finally:
        m._BASE = orig
        _reset_dedup(eid, cp)


def test_accumulate_no_duplica_con_y_sin_reply_context(tmp_path):
    """El mismo mensaje con y sin contexto de respuesta debe deduplicarse."""
    from graphs.nodes import summarize as m
    orig = m._BASE
    m._BASE = tmp_path
    try:
        eid, cp = "e2", "c2"
        _reset_dedup(eid, cp)
        from datetime import datetime
        ts = datetime(2026, 5, 13, 14, 48)
        # Scraper: con reply context
        accumulate(eid, cp, "Andrés", "text", "Andrés: Brillante\n> ↩ [Jozbuyo] buenísimo! yo estoy avanzando", timestamp=ts)
        # Sync-DB: sin reply context
        accumulate(eid, cp, "Andrés", "text", "Andrés: Brillante", timestamp=ts)
        assert m._path(eid, cp).read_text().count("---\n") == 1, "Brillante con/sin reply context no debe duplicarse"
    finally:
        m._BASE = orig
        _reset_dedup(eid, cp)


# ── Tests de _iter_entry_hashes e invalidate_dedup ────────────────────────────

def test_iter_entry_hashes_basico(tmp_path):
    """Cada entrada del .md produce exactamente un hash; multi-línea cuenta como una."""
    md = tmp_path / "chat.md"
    md.write_text(textwrap.dedent("""\
        ## 2026-05-13 10:00
        **[text]** José: Hola
        ---
        ## 2026-05-13 10:01
        **[text]** Andrés: Bien
        segunda línea del mismo mensaje
        ---
        ## 2026-05-13 10:02
        **[text]** José: último sin separador
    """), encoding="utf-8")
    hashes = list(_iter_entry_hashes(md))
    assert len(hashes) == 3
    assert len(set(hashes)) == 3, "mensajes distintos → hashes distintos"


def test_iter_entry_hashes_archivo_vacio(tmp_path):
    md = tmp_path / "chat.md"
    md.write_text("", encoding="utf-8")
    assert list(_iter_entry_hashes(md)) == []


def test_invalidate_dedup_contacto_y_empresa():
    _dedup[("emp_x", "c1")] = {"h1"}
    _dedup_loaded.add(("emp_x", "c1"))
    _dedup[("emp_x", "c2")] = {"h2"}
    _dedup_loaded.add(("emp_x", "c2"))
    _dedup[("emp_y", "c1")] = {"h3"}
    _dedup_loaded.add(("emp_y", "c1"))

    invalidate_dedup("emp_x", "c1")
    assert ("emp_x", "c1") not in _dedup_loaded
    assert ("emp_x", "c2") in _dedup_loaded, "otro contacto no se invalida"

    invalidate_dedup("emp_x")  # toda la empresa
    assert ("emp_x", "c2") not in _dedup_loaded
    assert ("emp_y", "c1") in _dedup_loaded, "otra empresa no se invalida"

    invalidate_dedup("emp_y", "c1")  # cleanup


# ── Tests de _parse_messages ──────────────────────────────────────────────────

def test_parse_messages_multiline_text():
    """Mensajes con múltiples líneas deben conservar todo el contenido, no solo la primera."""
    md = textwrap.dedent("""\
        ## 2026-05-13 14:49
        **[text]** Andrés Buxareo: Bien
        Mi viaje es en realidad a San Isidro a una Veleria.
        Luego si crees conveniente me acerco por allí. O puede ser para una futura visita.
        ---
        ## 2026-05-13 14:48
        **[text]** Andrés Buxareo: Brillante
        ---
    """)
    msgs = _parse_messages(md, "emp_test", "5491100000000")
    assert len(msgs) == 2
    multiline_msg = next((m for m in msgs if "Bien" in m.get("content", "")), None)
    assert multiline_msg is not None, "Mensaje multi-línea no encontrado"
    assert "Mi viaje es en realidad a San Isidro" in multiline_msg["content"], (
        f"Línea de continuación truncada. content={multiline_msg['content']!r}"
    )
    assert "Luego si crees conveniente" in multiline_msg["content"], (
        f"Segunda línea de continuación truncada. content={multiline_msg['content']!r}"
    )


def test_parse_messages_single_line_unchanged():
    """Mensajes de una sola línea no deben verse afectados por el fix."""
    md = textwrap.dedent("""\
        ## 2026-05-13 10:00
        **[text]** José: Hola, cómo estás?
        ---
        ## 2026-05-13 10:01
        **[text]** Andrés: Bien, gracias
        ---
    """)
    msgs = _parse_messages(md, "emp_test", "5491100000000")
    assert len(msgs) == 2
    contents = [m.get("content", "") for m in msgs]
    assert any("Hola, cómo estás?" in c for c in contents)
    assert any("Bien, gracias" in c for c in contents)


def test_parse_messages_image_with_sender():
    """Imagen con sender debe parsearse como tipo image."""
    md = textwrap.dedent("""\
        ## 2026-05-11 17:09
        **[image]** Andrés Buxareo: [imagen guardada: img_abc123.jpg]
        ---
        ## 2026-05-11 17:10
        **[image]** Andrés Buxareo: [imagen]
        ---
    """)
    msgs = _parse_messages(md, "emp_test", "5491100000000")
    assert len(msgs) == 2
    assert all(m["type"] == "image" for m in msgs)
    assert msgs[0].get("filename") == "img_abc123.jpg"


def test_parse_messages_image_pending_not_in_output():
    """image_pending nunca debe aparecer en los mensajes finales del parser."""
    md = textwrap.dedent("""\
        ## 2026-05-11 16:58
        **[image]** Andrés Buxareo: [imagen guardada: img_aabbcc.jpg]
        ---
    """)
    msgs = _parse_messages(md, "emp_test", "5491100000000")
    assert len(msgs) == 1
    assert msgs[0]["type"] == "image"


def test_parse_messages_image_with_caption():
    """Imagen con caption debe retornar filename y caption separados."""
    md = textwrap.dedent("""\
        ## 2026-05-07 16:58
        **[image]** Andrés Buxareo: [imagen guardada: img_abc123.jpg] — Antecedentes = sobre lo que trabajé en 2005 a 2009
        ---
        ## 2026-05-07 16:59
        **[image]** Andrés Buxareo: [imagen guardada: img_def456.jpg]
        ---
    """)
    msgs = _parse_messages(md, "emp_test", "5491100000000")
    assert len(msgs) == 2
    assert msgs[0]["filename"] == "img_abc123.jpg"
    assert msgs[0]["caption"] == "Antecedentes = sobre lo que trabajé en 2005 a 2009"
    assert msgs[0]["sender"] == "Andrés Buxareo"
    assert msgs[1]["filename"] == "img_def456.jpg"
    assert msgs[1].get("caption") is None


def test_parse_messages_image_without_caption():
    """Imagen sin caption no debe tener campo caption."""
    md = textwrap.dedent("""\
        ## 2026-05-07 17:00
        **[image]** Tú: [imagen guardada: img_xyz.jpg]
        ---
    """)
    msgs = _parse_messages(md, "emp_test", "5491100000000")
    assert len(msgs) == 1
    assert msgs[0]["filename"] == "img_xyz.jpg"
    assert msgs[0].get("caption") is None
