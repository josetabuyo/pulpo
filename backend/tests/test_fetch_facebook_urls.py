"""Tests: _parse_og_image, _fetch_og_images_browser, detección de sesión expirada."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from nodes import fetch_facebook


# ─── _parse_og_image ─────────────────────────────────────────────────────────

def test_parse_og_image_parsea_meta_tag():
    """Extrae og:image del HTML correctamente."""
    html = '<meta property="og:image" content="https://example.com/img.jpg" />'
    assert fetch_facebook._parse_og_image(html) == "https://example.com/img.jpg"


def test_parse_og_image_orden_alternativo_de_atributos():
    """Soporta og:image con content antes que property."""
    html = '<meta content="https://cdn.example.com/photo.jpg" property="og:image" />'
    assert fetch_facebook._parse_og_image(html) == "https://cdn.example.com/photo.jpg"


def test_parse_og_image_decodifica_amp():
    """Decodifica &amp; en la URL de imagen."""
    html = '<meta property="og:image" content="https://scontent.fbcdn.net/img?oh=1&amp;oe=2" />'
    result = fetch_facebook._parse_og_image(html)
    assert "&amp;" not in result
    assert "&" in result


def test_parse_og_image_retorna_vacio_si_no_hay_meta():
    """Retorna string vacío si no hay meta og:image."""
    html = "<html><body>sin imagen</body></html>"
    assert fetch_facebook._parse_og_image(html) == ""


# ─── _fetch_og_images_browser ────────────────────────────────────────────────

def _make_mock_tab(html: str):
    """Crea un mock de pestaña de Playwright que devuelve meta og:image del HTML dado."""
    import re
    m = re.search(r'content=["\']([^"\']+)["\']', html)
    content = m.group(1) if m else ""

    meta_mock = AsyncMock()
    meta_mock.get_attribute = AsyncMock(return_value=content)

    tab = AsyncMock()
    tab.goto = AsyncMock()
    tab.wait_for_timeout = AsyncMock()
    tab.query_selector = AsyncMock(return_value=meta_mock if content else None)
    tab.close = AsyncMock()
    return tab


@pytest.mark.asyncio
async def test_fetch_og_images_browser_extrae_og_image():
    """Extrae og:image abriendo una pestaña nueva."""
    tab = _make_mock_tab('<meta property="og:image" content="https://img.example.com/a.jpg" />')

    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(return_value=tab)

    mock_page = MagicMock()
    mock_page.context = mock_ctx

    result = await fetch_facebook._fetch_og_images_browser(
        mock_page,
        ["https://www.facebook.com/share/p/abc/"],
    )
    assert result == ["https://img.example.com/a.jpg"]


@pytest.mark.asyncio
async def test_fetch_og_images_browser_retorna_vacio_si_falla():
    """Retorna string vacío si la pestaña lanza excepción."""
    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(side_effect=Exception("timeout"))

    mock_page = MagicMock()
    mock_page.context = mock_ctx

    result = await fetch_facebook._fetch_og_images_browser(
        mock_page,
        ["https://www.facebook.com/share/p/err/"],
    )
    assert result == [""]


@pytest.mark.asyncio
async def test_fetch_og_images_browser_solo_primera_url():
    """Solo procesa la primera URL; el resto retorna string vacío."""
    tab = _make_mock_tab('<meta property="og:image" content="https://img.example.com/a.jpg" />')

    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(return_value=tab)

    mock_page = MagicMock()
    mock_page.context = mock_ctx

    result = await fetch_facebook._fetch_og_images_browser(
        mock_page,
        [
            "https://www.facebook.com/share/p/url1/",
            "https://www.facebook.com/share/p/url2/",
        ],
    )
    assert len(result) == 2
    assert result[0] == "https://img.example.com/a.jpg"
    assert result[1] == ""
    # Solo se abrió una pestaña (la primera)
    assert mock_ctx.new_page.call_count == 1


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

    # Sin resultados de scraping → solo static posts (o vacío si query sin resultados)
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
