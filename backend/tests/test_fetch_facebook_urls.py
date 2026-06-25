"""Tests: extracción de share URLs, detección de sesión expirada."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from nodes import fetch_facebook


@pytest.fixture(autouse=True)
def mock_fb_cache_module():
    """Aísla la cache SQLite — estos tests solo prueban lógica de fetch_facebook."""
    mock = MagicMock()
    mock.get_by_query = AsyncMock(return_value=[])
    mock.get_urls = AsyncMock(return_value=set())
    mock.save = AsyncMock(return_value=None)
    with patch.object(fetch_facebook, "_fb_cache", mock):
        yield mock


# ─── Detección de sesión expirada ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_posts_devuelve_vacio_si_no_hay_login():
    """
    Si _load_posts retorna [] (cookies expiradas), fetch_posts
    no retorna posts scrapeados pero sí los static posts de luganense.
    """
    fetch_facebook.invalidate("luganense")
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=[])):
        posts = await fetch_facebook.fetch_posts("luganense", "murguiondo")

    assert isinstance(posts, list)
    for p in posts:
        assert "text" in p
        assert "url" in p


# ─── Estructura de posts scrapeados ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_posts_incluye_url_de_post():
    """fetch_posts incluye la url del post scrapeado."""
    fetch_facebook.invalidate("luganense_url")
    scraped = [{"text": "Test post", "image_url": "", "url": "https://www.facebook.com/share/p/abc123/"}]
    with patch.object(fetch_facebook, "_load_posts", new=AsyncMock(return_value=scraped)):
        posts = await fetch_facebook.fetch_posts("luganense_url", "test")

    posts_con_url = [p for p in posts if "share/p/" in p.get("url", "")]
    assert len(posts_con_url) >= 1
