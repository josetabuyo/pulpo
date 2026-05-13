"""
Tests para import-wa-history con reintentos.

Los tests unitarios (_build_skip_set, _count_md_entries) no requieren server.
Los tests de integración requieren el server corriendo en el puerto del .env.
"""
import textwrap
import pytest
from pathlib import Path
from conftest import ADMIN, ADMIN_PASSWORD

GARANTIDO_FLOW = "55f90118-a6f5-4c04-b775-b503a6748bfe"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_chat_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


# ── Importar funciones bajo test directamente (no pasan por app completa) ─────
# Deben vivir en api/flows.py con signatura (md_path: Path) → portables sin mock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api.flows import _build_skip_set, _count_md_entries
from graphs.nodes.summarize import accumulate, _dedup, _dedup_loaded
from api.summarizer import _parse_messages


# ── Tests unitarios ───────────────────────────────────────────────────────────

def test_build_skip_set_empty_when_no_file(tmp_path):
    """Sin chat.md → set vacío."""
    result = _build_skip_set(tmp_path / "noexiste.md")
    assert result == set()


def test_build_skip_set_captures_ok_audios(tmp_path):
    """Audios con transcripción real deben aparecer en el skip set."""
    md = tmp_path / "chat.md"
    _write_chat_md(md, """\
        ## 2026-05-04 14:22
        **[audio]** Andrés Buxareo: Hola José, cómo estás
        ---
        ## 2026-05-04 14:23
        **[text]** Andrés Buxareo: Gracias
        ---
        ## 2026-05-05 17:21
        **[audio]** Tú: Bueno Andrés, fue un gusto
        ---
    """)
    result = _build_skip_set(md)
    assert "2026-05-04 14:22" in result   # audio ok → skip
    assert "2026-05-05 17:21" in result   # audio ok → skip
    assert "2026-05-04 14:23" not in result  # texto → no skip


def test_build_skip_set_excludes_failed_audios(tmp_path):
    """Audios con 'sin blob' o 'error' NO deben estar en el skip set (son reintentables)."""
    md = tmp_path / "chat.md"
    _write_chat_md(md, """\
        ## 2026-05-04 14:36
        **[audio]** Andrés Buxareo: [audio — sin blob]
        ---
        ## 2026-05-04 14:37
        **[audio]** Andrés Buxareo: [audio — error al transcribir]
        ---
        ## 2026-05-04 14:38
        **[audio]** Andrés Buxareo: Este sí tiene transcripción real
        ---
    """)
    result = _build_skip_set(md)
    assert "2026-05-04 14:36" not in result  # sin blob → reintentable
    assert "2026-05-04 14:37" not in result  # error → reintentable
    assert "2026-05-04 14:38" in result       # ok → skip


def test_count_md_entries_zero_when_no_file(tmp_path):
    assert _count_md_entries(tmp_path / "noexiste.md") == 0


def test_count_md_entries_counts_separators(tmp_path):
    md = tmp_path / "chat.md"
    _write_chat_md(md, """\
        ## 2026-05-04 14:22
        **[audio]** A: texto uno
        ---
        ## 2026-05-04 14:23
        **[text]** B: texto dos
        ---
    """)
    assert _count_md_entries(md) == 2


# ── Tests de enriquecimiento de placeholders ──────────────────────────────────

def _reset_dedup(empresa_id: str, contact_phone: str):
    key = (empresa_id, contact_phone)
    _dedup_loaded.discard(key)
    _dedup.pop(key, None)


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


# ── Tests de integración (requieren server corriendo) ─────────────────────────

def test_import_wa_history_responde_inmediato(client):
    """El endpoint responde con started sin esperar el scrape."""
    r = client.post(
        f"/api/empresas/garantido/flows/{GARANTIDO_FLOW}/import-wa-history",
        headers=ADMIN,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "started"
    assert "Andrés Buxareo" in data["contacts"]
    assert data["max_retries"] == 1


def test_import_wa_history_max_retries_param(client):
    """El parámetro max_retries se refleja en la respuesta."""
    r = client.post(
        f"/api/empresas/garantido/flows/{GARANTIDO_FLOW}/import-wa-history?max_retries=3",
        headers=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["max_retries"] == 3


def test_import_wa_history_max_retries_clamped(client):
    """max_retries fuera de rango se clampea a 10."""
    r = client.post(
        f"/api/empresas/garantido/flows/{GARANTIDO_FLOW}/import-wa-history?max_retries=99",
        headers=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["max_retries"] == 10


def test_import_wa_history_requiere_auth(client):
    """Sin password debe rechazar."""
    r = client.post(
        f"/api/empresas/garantido/flows/{GARANTIDO_FLOW}/import-wa-history",
    )
    assert r.status_code in (401, 403)


# ── Tests de _parse_messages (Bug 1: mensajes multi-línea) ────────────────────

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
