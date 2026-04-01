"""Tests unitarios: fetch_facebook loguea correctamente los posts scrapeados."""
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from nodes import fetch_facebook


@pytest.mark.asyncio
async def test_static_posts_aparecen_en_logs(caplog):
    """Los static posts deben loguearse aunque el browser falle."""
    with patch.object(fetch_facebook, "_load", new=AsyncMock(return_value="")):
        with caplog.at_level(logging.INFO, logger="nodes.fetch_facebook"):
            await fetch_facebook.fetch("luganense", "milanesas")

    mensajes = [r.message for r in caplog.records]
    assert any("[fetch_facebook] static 1:" in m for m in mensajes), (
        "Esperaba log '[fetch_facebook] static 1:' pero no se encontró"
    )


@pytest.mark.asyncio
async def test_log_incluye_primeras_80_chars(caplog):
    """El log de static post debe incluir los primeros 80 chars del texto (sin newlines)."""
    # Invalidar cache para que no devuelva un resultado cacheado
    fetch_facebook.invalidate("luganense")

    with patch.object(fetch_facebook, "_load", new=AsyncMock(return_value="")):
        with caplog.at_level(logging.INFO, logger="nodes.fetch_facebook"):
            await fetch_facebook.fetch("luganense", "polleria_test_log")

    static_logs = [
        r.message for r in caplog.records
        if "[fetch_facebook] static" in r.message
    ]
    assert static_logs, "No se encontraron logs de static posts"

    # El log no debe contener newlines (fue reemplazado por ' ')
    for msg in static_logs:
        assert "\n" not in msg, f"El log contiene newlines: {msg!r}"

    # El texto del log (la parte después del prefijo) no supera 80 chars
    for msg in static_logs:
        # formato: "[fetch_facebook] static N: <texto>"
        texto = msg.split(": ", 2)[-1]
        assert len(texto) <= 80, f"Texto del log supera 80 chars: {texto!r}"
