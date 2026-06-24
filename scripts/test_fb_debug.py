#!/usr/bin/env python3
"""
Script de integración: fetch Facebook + cache persistente.

Corre una serie de búsquedas y muestra el estado de fb_posts y fb_post_queries
después de cada una, para verificar que la cache acumula posts y queries.

Uso:
    python scripts/test_fb_debug.py                         # headless, queries predefinidas
    python scripts/test_fb_debug.py "perro perdido" "gato"  # queries custom
    python scripts/test_fb_debug.py --visible               # browser visible + pausa 60s
"""
import asyncio
import aiosqlite
import logging
import os
import sys
import time
from pathlib import Path

root = Path(__file__).parent.parent
sys.path.insert(0, str(root / "backend"))

args = sys.argv[1:]
if "--visible" in args:
    os.environ["FB_DEBUG"] = "1"
    args = [a for a in args if a != "--visible"]

env_file = root / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

PAGE_ID = "luganense"

DEFAULT_QUERIES = [
    "perro perdido",
    "accidente",
    "perro perdido",   # repetida a propósito — no debe duplicar la query en el post
]


def _fmt_time(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


async def show_cache():
    from nodes import fb_cache
    posts = await fb_cache.get_all(PAGE_ID)
    if not posts:
        print("  (tabla vacía)")
        return
    print(f"  {len(posts)} post(s) en cache:")
    for p in posts:
        url_short = p["url"].replace("https://www.facebook.com/", "fb/")
        text_preview = (p["text"][:90].replace("\n", " ") + "…") if p["text"] else "(sin texto)"
        queries_str = ", ".join(f'"{q}"' for q in p["queries"])
        print(f"\n  URL:     {url_short}")
        print(f"  Texto:   {text_preview}")
        print(f"  Queries: [{queries_str}]")
        print(f"  Visto:   first={_fmt_time(p['first_seen'])}  last={_fmt_time(p['last_seen'])}")


async def show_raw_tables():
    """Muestra fb_posts y fb_post_queries separadas."""
    from nodes import fb_cache
    db_path = fb_cache._DB_PATH
    if not db_path.exists():
        print("  (DB no existe aún)")
        return

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM fb_posts WHERE page_id = ?", (PAGE_ID,)) as cur:
            n_posts = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM fb_post_queries q JOIN fb_posts p ON p.url = q.url WHERE p.page_id = ?",
            (PAGE_ID,)
        ) as cur:
            n_queries = (await cur.fetchone())[0]

    print(f"  fb_posts: {n_posts} filas | fb_post_queries: {n_queries} filas")


async def run_verifications():
    """Verificaciones al final del script."""
    from nodes import fb_cache
    posts = await fb_cache.get_all(PAGE_ID)

    print("\n[VERIFICACIONES]")

    # 1. Ningún post con URL de fallback
    fallback = [p for p in posts if f"/{PAGE_ID}" == p["url"].rstrip("/").split("facebook.com")[-1]]
    if fallback:
        print(f"  ✗ FALLA: {len(fallback)} post(s) con URL de fallback (fb/{PAGE_ID})")
        for p in fallback:
            print(f"      {p['url']}")
    else:
        print(f"  ✓ Sin URLs de fallback (ningún fb/{PAGE_ID})")

    # 2. Al menos un post con permalink real (/posts/ o /share/p/)
    with_url = [p for p in posts if any(pat in p["url"] for pat in ("/posts/", "/share/p/", "/permalink.php"))]
    if with_url:
        print(f"  ✓ {len(with_url)} post(s) con permalink real")
    else:
        print("  ✗ FALLA: Ningún post con permalink real")

    # 3. Al menos un post aparece en dos queries distintas (proof of accumulation)
    multi_query = [p for p in posts if len(set(p["queries"])) >= 2]
    if multi_query:
        p = multi_query[0]
        print(f"  ✓ Post con múltiples queries: {p['url'][:60]} → {p['queries']}")
    else:
        if len(posts) > 0:
            print("  ⚠  Ningún post aparece en 2+ queries aún (ejecutar con más queries o repetir)")
        else:
            print("  ⚠  Cache vacía — no hay posts que verificar")

    # 4. Idempotencia: no hay duplicados en fb_post_queries
    from nodes import fb_cache
    db_path = fb_cache._DB_PATH
    if db_path.exists():
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT url, query, COUNT(*) as n FROM fb_post_queries GROUP BY url, query HAVING n > 1"
            ) as cur:
                dupes = await cur.fetchall()
        if dupes:
            print(f"  ✗ FALLA: {len(dupes)} combinación(es) url+query duplicadas en fb_post_queries")
        else:
            print("  ✓ Sin duplicados en fb_post_queries (UNIQUE funciona)")


async def main():
    from nodes import fetch_facebook

    queries = args if args else DEFAULT_QUERIES
    visible = bool(os.getenv("FB_DEBUG"))

    print(f"\n{'='*60}")
    print(f"  Página:  {PAGE_ID}")
    print(f"  Queries: {queries}")
    print(f"  Modo:    {'VISIBLE (--visible)' if visible else 'headless'}")
    print(f"{'='*60}")

    print("\n[ESTADO INICIAL DE CACHE]")
    await show_cache()
    await show_raw_tables()

    for i, query in enumerate(queries, 1):
        print(f"\n{'─'*60}")
        print(f"  [{i}/{len(queries)}] Buscando: '{query}'")
        print(f"{'─'*60}")

        # Invalidar cache en memoria para forzar re-scraping de FB en cada vuelta
        fetch_facebook.invalidate(PAGE_ID)

        posts = await fetch_facebook.fetch_posts(PAGE_ID, query)

        scrapeados = [p for p in posts if any(pat in p.get("url", "") for pat in ("/posts/", "/share/p/", "/permalink.php"))]
        print(f"\n  → {len(posts)} post(s) totales ({len(scrapeados)} scrapeados con permalink, {len(posts)-len(scrapeados)} otros)")
        for j, p in enumerate(posts, 1):
            url = p.get("url", "(sin url)")
            text = (p["text"][:100].replace("\n", " ") + "…") if p.get("text") else "(sin texto)"
            print(f"    [{j}] {url}")
            print(f"         {text}")

        print(f"\n[CACHE DESPUÉS DE QUERY #{i}: '{query}']")
        await show_cache()
        await show_raw_tables()

    await run_verifications()

    print(f"\n{'='*60}\n")


asyncio.run(main())
