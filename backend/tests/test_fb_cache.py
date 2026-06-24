"""
Tests unitarios para fb_cache.py.

No requieren servidor ni browser — solo SQLite.
Usan una DB temporal para no contaminar messages.db.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from nodes import fb_cache


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Cada test usa su propia DB vacía."""
    db = tmp_path / "fb_test.db"
    monkeypatch.setattr(fb_cache, "_DB_PATH", db)
    monkeypatch.setattr(fb_cache, "_tables_ready", False)
    yield db


# ─── save ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_nuevo_post():
    posts = [{"url": "https://fb.com/share/p/AAA/", "text": "Perro perdido", "image_url": ""}]
    await fb_cache.save("luganense", "perro perdido", posts)

    all_posts = await fb_cache.get_all("luganense")
    assert len(all_posts) == 1
    assert all_posts[0]["url"] == "https://fb.com/share/p/AAA/"
    assert all_posts[0]["text"] == "Perro perdido"
    assert "perro perdido" in all_posts[0]["queries"]


@pytest.mark.asyncio
async def test_save_no_duplica_url():
    post = {"url": "https://fb.com/share/p/AAA/", "text": "Texto", "image_url": ""}
    await fb_cache.save("luganense", "q1", [post])
    await fb_cache.save("luganense", "q2", [post])  # misma URL

    all_posts = await fb_cache.get_all("luganense")
    assert len(all_posts) == 1


@pytest.mark.asyncio
async def test_query_no_se_duplica():
    post = {"url": "https://fb.com/share/p/AAA/", "text": "Texto", "image_url": ""}
    await fb_cache.save("luganense", "perro perdido", [post])
    await fb_cache.save("luganense", "perro perdido", [post])  # repetida
    await fb_cache.save("luganense", "perro perdido", [post])  # repetida otra vez

    all_posts = await fb_cache.get_all("luganense")
    assert len(all_posts) == 1
    assert all_posts[0]["queries"].count("perro perdido") == 1


@pytest.mark.asyncio
async def test_acumula_queries_distintas():
    post = {"url": "https://fb.com/share/p/AAA/", "text": "Texto", "image_url": ""}
    await fb_cache.save("luganense", "perro perdido", [post])
    await fb_cache.save("luganense", "mascota perdida", [post])
    await fb_cache.save("luganense", "adopción", [post])

    all_posts = await fb_cache.get_all("luganense")
    assert len(all_posts) == 1
    queries = all_posts[0]["queries"]
    assert set(queries) == {"perro perdido", "mascota perdida", "adopción"}
    assert len(queries) == 3


@pytest.mark.asyncio
async def test_texto_mas_largo_gana():
    url = "https://fb.com/share/p/AAA/"
    await fb_cache.save("luganense", "q1", [{"url": url, "text": "Perro", "image_url": ""}])
    await fb_cache.save("luganense", "q2", [{"url": url, "text": "Perro negro perdido en Villa Lugano", "image_url": ""}])

    all_posts = await fb_cache.get_all("luganense")
    assert all_posts[0]["text"] == "Perro negro perdido en Villa Lugano"


@pytest.mark.asyncio
async def test_texto_largo_no_se_pisa():
    url = "https://fb.com/share/p/AAA/"
    await fb_cache.save("luganense", "q1", [{"url": url, "text": "Perro negro perdido en Villa Lugano", "image_url": ""}])
    await fb_cache.save("luganense", "q2", [{"url": url, "text": "Perro", "image_url": ""}])

    all_posts = await fb_cache.get_all("luganense")
    assert all_posts[0]["text"] == "Perro negro perdido en Villa Lugano"


@pytest.mark.asyncio
async def test_get_all_incluye_queries():
    posts = [
        {"url": "https://fb.com/share/p/AAA/", "text": "Post A", "image_url": ""},
        {"url": "https://fb.com/share/p/BBB/", "text": "Post B", "image_url": ""},
    ]
    await fb_cache.save("luganense", "perro", posts)
    await fb_cache.save("luganense", "accidente", [posts[0]])  # solo AAA en dos queries

    all_posts = await fb_cache.get_all("luganense")
    assert len(all_posts) == 2

    paa = next(p for p in all_posts if "AAA" in p["url"])
    pbb = next(p for p in all_posts if "BBB" in p["url"])
    assert set(paa["queries"]) == {"perro", "accidente"}
    assert pbb["queries"] == ["perro"]


@pytest.mark.asyncio
async def test_get_by_query():
    posts = [
        {"url": "https://fb.com/share/p/AAA/", "text": "Perro perdido", "image_url": ""},
        {"url": "https://fb.com/share/p/BBB/", "text": "Accidente en Riestra", "image_url": ""},
    ]
    await fb_cache.save("luganense", "perro perdido", [posts[0]])
    await fb_cache.save("luganense", "accidente", [posts[1]])

    result = await fb_cache.get_by_query("luganense", "perro perdido")
    assert len(result) == 1
    assert result[0]["url"] == "https://fb.com/share/p/AAA/"

    result2 = await fb_cache.get_by_query("luganense", "accidente")
    assert len(result2) == 1
    assert result2[0]["url"] == "https://fb.com/share/p/BBB/"


@pytest.mark.asyncio
async def test_filtra_por_page_id():
    post_a = {"url": "https://fb.com/share/p/AAA/", "text": "Post A", "image_url": ""}
    post_b = {"url": "https://fb.com/share/p/BBB/", "text": "Post B", "image_url": ""}

    await fb_cache.save("luganense", "q1", [post_a])
    await fb_cache.save("otra_pagina", "q1", [post_b])

    luganense = await fb_cache.get_all("luganense")
    otra = await fb_cache.get_all("otra_pagina")

    assert len(luganense) == 1
    assert luganense[0]["url"] == post_a["url"]
    assert len(otra) == 1
    assert otra[0]["url"] == post_b["url"]


@pytest.mark.asyncio
async def test_posts_sin_url_se_ignoran():
    posts = [
        {"url": "", "text": "Sin URL", "image_url": ""},
        {"url": None, "text": "URL None", "image_url": ""},
        {"text": "Sin campo url", "image_url": ""},
    ]
    await fb_cache.save("luganense", "q1", posts)
    all_posts = await fb_cache.get_all("luganense")
    assert len(all_posts) == 0
