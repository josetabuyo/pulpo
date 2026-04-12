"""Tests unitarios: fetch_facebook — logs y fetch_posts."""
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from nodes import fetch_facebook


# ─── Tests de logs (estáticos) ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_static_posts_aparecen_en_logs(caplog):
    """Los static posts se loguean cuando hay posts scrapeados."""
    fetch_facebook.invalidate("luganense")
    scraped = [{"text": "Post scrapeado", "image_url": "", "url": ""}]
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=scraped)):
        with caplog.at_level(logging.INFO, logger="nodes.fetch_facebook"):
            await fetch_facebook.fetch("luganense", "milanesas")

    mensajes = [r.message for r in caplog.records]
    assert any("[fetch_facebook] static 1:" in m for m in mensajes), (
        "Esperaba log '[fetch_facebook] static 1:' pero no se encontró"
    )


@pytest.mark.asyncio
async def test_log_incluye_primeras_80_chars(caplog):
    """El log de static post no debe tener newlines y no superar 80 chars."""
    fetch_facebook.invalidate("luganense")
    scraped = [{"text": "Post scrapeado", "image_url": "", "url": ""}]
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=scraped)):
        with caplog.at_level(logging.INFO, logger="nodes.fetch_facebook"):
            await fetch_facebook.fetch("luganense", "polleria_test_log")

    static_logs = [r.message for r in caplog.records if "[fetch_facebook] static" in r.message]
    assert static_logs, "No se encontraron logs de static posts"

    for msg in static_logs:
        assert "\n" not in msg, f"El log contiene newlines: {msg!r}"
        texto = msg.split(": ", 2)[-1]
        assert len(texto) <= 80, f"Texto del log supera 80 chars: {texto!r}"


# ─── Tests de fetch_posts ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_posts_retorna_lista_de_dicts():
    """fetch_posts retorna lista de dicts con text e image_url cuando hay resultados."""
    fetch_facebook.invalidate("luganense")
    scraped = [{"text": "Post de prueba", "image_url": "", "url": ""}]
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=scraped)):
        posts = await fetch_facebook.fetch_posts("luganense", "test")

    assert isinstance(posts, list)
    assert len(posts) >= 1
    for p in posts:
        assert "text" in p
        assert "image_url" in p


@pytest.mark.asyncio
async def test_fetch_posts_incluye_imagen_del_scraping():
    """fetch_posts incluye la image_url que devuelve _load_posts."""
    fetch_facebook.invalidate("luganense_img")

    scraped = [{"text": "Perro perdido, zona Lugano", "image_url": "https://scontent.fbcdn.net/v/fake.jpg"}]
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=scraped)):
        posts = await fetch_facebook.fetch_posts("luganense_img", "perro")

    posts_con_imagen = [p for p in posts if p["image_url"]]
    assert len(posts_con_imagen) >= 1
    assert posts_con_imagen[0]["image_url"] == "https://scontent.fbcdn.net/v/fake.jpg"


@pytest.mark.asyncio
async def test_fetch_backward_compat():
    """fetch() sigue retornando str (compatibilidad con código existente)."""
    fetch_facebook.invalidate("luganense_compat")

    scraped = [{"text": "Post de prueba", "image_url": ""}]
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=scraped)):
        result = await fetch_facebook.fetch("luganense_compat", "prueba")

    assert isinstance(result, str)
    assert "Post de prueba" in result


@pytest.mark.asyncio
async def test_invalidate_limpia_cache():
    """invalidate() limpia _posts_cache para la página indicada."""
    fetch_facebook.invalidate("luganense_inv")

    scraped = [{"text": "Post de prueba", "image_url": ""}]
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=scraped)):
        await fetch_facebook.fetch_posts("luganense_inv", "query1")

    assert any(k.startswith("luganense_inv:") for k in fetch_facebook._posts_cache)
    fetch_facebook.invalidate("luganense_inv")
    assert not any(k.startswith("luganense_inv:") for k in fetch_facebook._posts_cache)
