"""
Node: fb_cache

Cache persistente de posts de Facebook en SQLite.
Schema normalizado: fb_posts + fb_post_queries(url, query, UNIQUE).

Interfaz pública:
  save(page_id, query, posts)          — upsert de posts
  get_all(page_id)                     — todos los posts con sus queries
  get_by_query(page_id, query)         — posts que salieron para esa query

_DB_PATH y _tables_ready son patcheables por tests (monkeypatch).
"""
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.getenv("FB_CACHE_DB", str(Path(__file__).parent.parent.parent / "data" / "messages.db")))
_tables_ready = False


# ─── Init ────────────────────────────────────────────────────────────────────

async def _init() -> None:
    global _tables_ready
    if _tables_ready:
        return
    await _ensure_tables()
    await _migrate_legacy()
    _tables_ready = True


async def _ensure_tables() -> None:
    import aiosqlite
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fb_posts (
                url        TEXT PRIMARY KEY,
                page_id    TEXT NOT NULL,
                text       TEXT NOT NULL DEFAULT '',
                image_url  TEXT NOT NULL DEFAULT '',
                first_seen REAL NOT NULL,
                last_seen  REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fb_post_queries (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                url      TEXT NOT NULL REFERENCES fb_posts(url) ON DELETE CASCADE,
                query    TEXT NOT NULL,
                found_at REAL NOT NULL,
                UNIQUE(url, query)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_fb_posts_page ON fb_posts(page_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_fbpq_url ON fb_post_queries(url)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_fbpq_query ON fb_post_queries(query)")
        await db.commit()


async def _migrate_legacy() -> None:
    """Migra datos de fb_posts.queries (JSON array) a la tabla fb_post_queries."""
    import json
    import aiosqlite
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("PRAGMA table_info(fb_posts)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "queries" not in cols:
            return

        async with db.execute("SELECT url, queries FROM fb_posts WHERE queries != '[]'") as cur:
            rows = await cur.fetchall()

        now = time.time()
        for url, queries_json in rows:
            try:
                for q in json.loads(queries_json):
                    await db.execute(
                        "INSERT OR IGNORE INTO fb_post_queries (url, query, found_at) VALUES (?, ?, ?)",
                        (url, q, now),
                    )
            except Exception:
                pass

        await db.execute("ALTER TABLE fb_posts RENAME TO fb_posts_old")
        await db.execute("""
            CREATE TABLE fb_posts (
                url TEXT PRIMARY KEY, page_id TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '',
                first_seen REAL NOT NULL, last_seen REAL NOT NULL
            )
        """)
        await db.execute("""
            INSERT INTO fb_posts
            SELECT url, page_id, text, image_url, first_seen, last_seen
            FROM fb_posts_old
        """)
        await db.execute("DROP TABLE fb_posts_old")
        await db.commit()
    logger.info("[fb_cache] migración de schema completada")


# ─── Interfaz pública ────────────────────────────────────────────────────────

async def save(page_id: str, query: str, posts: list[dict]) -> None:
    """
    Upsert de posts. El texto más largo gana. No duplica (url, query).
    Posts sin URL se ignoran.
    """
    if not posts:
        return
    import aiosqlite
    await _init()
    now = time.time()
    saved = 0
    async with aiosqlite.connect(_DB_PATH) as db:
        for post in posts:
            url = (post.get("url") or "").strip()
            if not url:
                continue
            text = post.get("text", "")
            image_url = post.get("image_url", "")

            await db.execute(
                "INSERT OR IGNORE INTO fb_posts (url, page_id, text, image_url, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (url, page_id, text, image_url, now, now),
            )
            await db.execute(
                "UPDATE fb_posts SET last_seen = ? WHERE url = ?",
                (now, url),
            )
            await db.execute(
                "UPDATE fb_posts SET text = ? WHERE url = ? AND length(?) > length(text)",
                (text, url, text),
            )
            if query:
                await db.execute(
                    "INSERT OR IGNORE INTO fb_post_queries (url, query, found_at) VALUES (?, ?, ?)",
                    (url, query, now),
                )
            saved += 1

        await db.commit()
    logger.info("[fb_cache] save: %d posts (query='%s')", saved, query)


async def get_all(page_id: str) -> list[dict]:
    """Todos los posts de una página con sus queries, ordenados por last_seen."""
    import aiosqlite
    await _init()
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT url, text, image_url, first_seen, last_seen FROM fb_posts "
            "WHERE page_id = ? ORDER BY last_seen DESC",
            (page_id,),
        ) as cur:
            posts_rows = await cur.fetchall()

        result = []
        for row in posts_rows:
            url = row[0]
            async with db.execute(
                "SELECT query FROM fb_post_queries WHERE url = ? ORDER BY found_at",
                (url,),
            ) as cur2:
                queries = [r[0] for r in await cur2.fetchall()]
            result.append({
                "url": url,
                "text": row[1],
                "image_url": row[2],
                "queries": queries,
                "first_seen": row[3],
                "last_seen": row[4],
            })
    return result


async def get_by_query(page_id: str, query: str) -> list[dict]:
    """Posts que alguna vez aparecieron para esa query."""
    import aiosqlite
    await _init()
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT p.url, p.text, p.image_url, p.first_seen, p.last_seen "
            "FROM fb_posts p "
            "JOIN fb_post_queries q ON q.url = p.url "
            "WHERE p.page_id = ? AND q.query = ? "
            "ORDER BY p.last_seen DESC",
            (page_id, query),
        ) as cur:
            rows = await cur.fetchall()
    return [
        {
            "url": r[0],
            "text": r[1],
            "image_url": r[2],
            "first_seen": r[3],
            "last_seen": r[4],
        }
        for r in rows
    ]
