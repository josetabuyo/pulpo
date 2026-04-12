"""Tests: extracción de share URLs, og:images, detección de sesión expirada."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from nodes import fetch_facebook


# ─── _fetch_og_images ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_og_images_parsea_meta_tag():
    """Extrae og:image del HTML de respuesta correctamente."""
    html = '<meta property="og:image" content="https://example.com/img.jpg" />'
    mock_resp = MagicMock()
    mock_resp.text = html

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await fetch_facebook._fetch_og_images(["https://www.facebook.com/share/p/abc/"])

    assert result == ["https://example.com/img.jpg"]


@pytest.mark.asyncio
async def test_fetch_og_images_orden_alternativo_de_atributos():
    """Soporta og:image con content antes que property."""
    html = '<meta content="https://cdn.example.com/photo.jpg" property="og:image" />'
    mock_resp = MagicMock()
    mock_resp.text = html

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await fetch_facebook._fetch_og_images(["https://www.facebook.com/share/p/xyz/"])

    assert result == ["https://cdn.example.com/photo.jpg"]


@pytest.mark.asyncio
async def test_fetch_og_images_decodifica_amp():
    """Decodifica &amp; en la URL de imagen."""
    html = '<meta property="og:image" content="https://scontent.fbcdn.net/img?oh=1&amp;oe=2" />'
    mock_resp = MagicMock()
    mock_resp.text = html

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await fetch_facebook._fetch_og_images(["https://www.facebook.com/share/p/test/"])

    assert "&amp;" not in result[0]
    assert "&" in result[0]


@pytest.mark.asyncio
async def test_fetch_og_images_retorna_vacio_si_falla():
    """Retorna string vacío si el request falla."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await fetch_facebook._fetch_og_images(["https://www.facebook.com/share/p/err/"])

    assert result == [""]


@pytest.mark.asyncio
async def test_fetch_og_images_paralelo_multiples_urls():
    """Procesa múltiples URLs en paralelo y mantiene orden."""
    html_a = '<meta property="og:image" content="https://img.example.com/a.jpg" />'
    html_b = '<meta property="og:image" content="https://img.example.com/b.jpg" />'

    call_count = 0

    async def fake_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.text = html_a if "url1" in url else html_b
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = fake_get

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await fetch_facebook._fetch_og_images([
            "https://www.facebook.com/share/p/url1/",
            "https://www.facebook.com/share/p/url2/",
        ])

    assert len(result) == 2
    assert result[0] == "https://img.example.com/a.jpg"
    assert result[1] == "https://img.example.com/b.jpg"


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


