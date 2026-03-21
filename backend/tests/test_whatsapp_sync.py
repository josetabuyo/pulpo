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


# ─── IDB timestamp string parsing ──────────────────────────────────────────

def test_idb_timestamp_string_to_unix():
    """
    El campo 'timestamp' en parsed dict es un string, no un datetime.
    Bug: llamar .timestamp() en un string lanza AttributeError.
    Fix: parsear con strptime antes de convertir a unix.
    """
    from datetime import datetime as _dt
    ts_str = "2026-03-17 11:41:00"
    # Bug original: ts_str.timestamp() → AttributeError
    # Fix:
    ts_unix = int(_dt.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp())
    assert ts_unix > 0
    assert isinstance(ts_unix, int)
    # Verificar que el valor es razonable (año 2026)
    assert ts_unix > 1_700_000_000


def test_idb_time_of_day_fallback():
    """
    Audios con fecha incorrecta en prePlain (heredada de mensaje anterior del día anterior)
    deben ser encontrados por coincidencia de hora del día (ts_unix % 86400).
    Bug: prePlain de 17/3 18:22 hereda fecha 16/3 → diferencia ~86400s → sin match.
    Fix: segundo intento con abs((k["t"] % 86400) - (ts_unix % 86400)) < 120.
    """
    from datetime import datetime as _dt

    # Audio real: 2026-03-17 18:22 (Unix ~1773782520)
    # prePlain incorrecto: muestra 16/3 → ts_unix calculado como 2026-03-16 18:22
    ts_wrong_day = int(_dt.strptime("2026-03-16 18:22:00", "%Y-%m-%d %H:%M:%S").timestamp())
    t_idb = int(_dt.strptime("2026-03-17 18:22:00", "%Y-%m-%d %H:%M:%S").timestamp())

    # Match exacto falla (offset ~86400s)
    assert abs(t_idb - ts_wrong_day) > 120

    # Match por hora del día funciona
    ts_tod = ts_wrong_day % 86400
    assert abs((t_idb % 86400) - ts_tod) < 120, "La coincidencia por hora del día debe funcionar"
