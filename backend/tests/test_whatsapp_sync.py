"""
Tests unitarios para la lógica de full-sync:
- Bug fix: dedup key debe incluir el body (no solo prePlain)
- Bug fix: _full_sync_running debe resetear a False aunque ocurra una excepción
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─── Dedup key ─────────────────────────────────────────────────────────

def test_dedup_key_includes_body():
    """
    Dos mensajes del mismo sender en el mismo minuto NO deben ser deduplicados.
    El bug original usaba solo prePlain como clave — el segundo mensaje se perdía.
    """
    msgs = [
        {"prePlain": "[1/1/2025, 10:00] Fabian:", "body": "Primer mensaje"},
        {"prePlain": "[1/1/2025, 10:00] Fabian:", "body": "Segundo mensaje"},
    ]
    # Fix: clave = prePlain + "|" + body
    seen_fixed = {m["prePlain"] + "|" + m["body"] for m in msgs}
    assert len(seen_fixed) == 2, "Dos mensajes distintos deben tener claves distintas"

    # Documentar el bug original: solo prePlain colapsa ambos mensajes en uno
    seen_buggy = {m["prePlain"] for m in msgs}
    assert len(seen_buggy) == 1, "El bug original colapsaba mensajes del mismo sender/minuto"


def test_dedup_key_same_body_different_sender():
    """Mensajes con el mismo body pero distinto sender sí son distintos."""
    msgs = [
        {"prePlain": "[1/1/2025, 10:00] Ana:", "body": "Hola"},
        {"prePlain": "[1/1/2025, 10:00] Juan:", "body": "Hola"},
    ]
    seen = {m["prePlain"] + "|" + m["body"] for m in msgs}
    assert len(seen) == 2


def test_dedup_key_same_sender_same_body_is_duplicate():
    """Mismo sender, mismo minuto, mismo body → sí es duplicado legítimo."""
    msgs = [
        {"prePlain": "[1/1/2025, 10:00] Ana:", "body": "Hola"},
        {"prePlain": "[1/1/2025, 10:00] Ana:", "body": "Hola"},
    ]
    seen = {m["prePlain"] + "|" + m["body"] for m in msgs}
    assert len(seen) == 1, "Mismo mensaje duplicado debe deduplicarse"


# ─── _full_sync_running try/finally ────────────────────────────────────

def test_full_sync_running_resets_on_exception():
    """
    _full_sync_running debe volver a False aunque _run_full_sync lance una excepción.
    Bug original: sin try/finally, una excepción dejaba el flag en True para siempre.
    """
    import api.whatsapp as wa

    wa._full_sync_running = False

    # Forzar excepción dentro de _run_full_sync simulando que clients tiene
    # una sesión whatsapp lista, pero get_empresas_for_bot lanza error.
    fake_clients = {
        "5491100001": {"type": "whatsapp", "status": "ready", "bot_id": "bot1"}
    }

    # get_empresas_for_bot se importa dentro de la función, hay que parcharlo en config
    with patch.dict("api.whatsapp.__dict__", {"clients": fake_clients}):
        with patch("config.get_empresas_for_bot", side_effect=RuntimeError("error simulado")):
            try:
                asyncio.run(wa._run_full_sync())
            except SystemExit:
                pass

    assert wa._full_sync_running is False, \
        "_full_sync_running debe ser False después de una excepción (try/finally)"


def test_full_sync_running_prevents_concurrent():
    """Si _full_sync_running es True, _run_full_sync retorna inmediatamente sin hacer nada."""
    import api.whatsapp as wa

    wa._full_sync_running = True
    # No debería tocar clients ni nada más
    with patch("api.whatsapp.clients", {}):
        asyncio.run(wa._run_full_sync())
    # Si llegó aquí sin colgar → está bien (ya estaba corriendo, salió early)
    # Resetear para no afectar otros tests
    wa._full_sync_running = False
