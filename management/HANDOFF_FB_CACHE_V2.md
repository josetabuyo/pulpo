# Handoff: Cache persistente FB — iteración 2

**Fecha:** 2026-06-24  
**Contexto:** nodo fetch_facebook del graph Luganense  
**Worktree:** `_` (master/producción)

---

## Estado al terminar esta sesión

Se implementó una primera versión de cache persistente en SQLite para los posts
de Facebook que scrapeamos. Funciona, pero tiene tres problemas graves que esta
iteración debe resolver antes de que la cache sea usable como fuente de respuestas.

### Lo que quedó hecho (no tocar):
- Tests unitarios: `backend/tests/test_fb_cache.py` — 10/10 verdes
- Tests existentes de fetch_facebook: 8/8 verdes
- Script de integración: `scripts/test_fb_debug.py`

### Los tres problemas a resolver:

**Problema 1 — URL de fallback inútil**  
Cuando `_extract_post_urls` no logra capturar ninguna URL via "Compartir → Copiar enlace",
el código guarda `https://www.facebook.com/luganense` como URL del post. Ese link lleva
a la página entera, no al post. Es inútil como referencia y contamina la cache.

**Problema 2 — Extracción de URLs por "Compartir" es frágil**  
El mecanismo actual hace click en el botón "Compartir" → "Copiar enlace" y captura la
URL del evento de red. Falla en la mayoría de posts (ver logs: "post N: no se capturó
share URL"). En la búsqueda de "accidente" falló 3/3 veces.

**Problema 3 — Solo el primer post tiene texto**  
En `_search_and_scrape`, el texto del feed completo se asigna solo al primer post:
`"text": text if i == 0 else ""`. Los otros posts solo tienen URL vacía. En la cache
quedan posts con `text = ""` que no sirven para responder.

**Problema 4 — Responsabilidades mezcladas**  
La lógica de cache (tablas, upsert, queries) está incrustada dentro de `fetch_facebook.py`.
Viola SRP. Hay que separarla en su propio módulo.

**Problema 5 — Schema no normalizado**  
Las queries se guardan como JSON array en la columna `queries` de `fb_posts`. Lo correcto
es una tabla relacional `fb_post_queries(url, query)` con UNIQUE(url, query).

---

## Arquitectura objetivo

### Módulos

```
backend/nodes/fetch_facebook.py   — SOLO scraping (Playwright)
backend/nodes/fb_cache.py         — SOLO persistencia (SQLite) ← NUEVO
backend/graphs/luganense.py       — orquestación: llama a ambos
```

**`fetch_facebook.py`** no toca la DB. Su única responsabilidad es:
recibir `(page_id, query)` → devolver `list[dict]` con `{url, text, image_url}`.
Cada dict DEBE tener una URL real y clickeable. Si no puede obtenerla, no incluye el post.

**`fb_cache.py`** no sabe nada de Playwright. Su única responsabilidad es:
guardar y consultar posts en SQLite.

**`luganense.py`** en `buscar_posts_fb`:
1. Llama a `fetch_facebook.fetch_posts()` → obtiene posts frescos de FB
2. Llama a `fb_cache.save()` → los persiste
3. Llama a `fb_cache.get_by_query()` → obtiene lo acumulado para esa query

### Schema de tablas

```sql
-- Posts únicos (por URL)
CREATE TABLE IF NOT EXISTS fb_posts (
    url        TEXT PRIMARY KEY,
    page_id    TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    image_url  TEXT NOT NULL DEFAULT '',
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL
);

-- Relación post ↔ query (normalizada)
CREATE TABLE IF NOT EXISTS fb_post_queries (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    url      TEXT NOT NULL REFERENCES fb_posts(url) ON DELETE CASCADE,
    query    TEXT NOT NULL,
    found_at REAL NOT NULL,
    UNIQUE(url, query)            -- ← garantiza no duplicar
);

CREATE INDEX IF NOT EXISTS idx_fb_posts_page    ON fb_posts(page_id);
CREATE INDEX IF NOT EXISTS idx_fbpq_url         ON fb_post_queries(url);
CREATE INDEX IF NOT EXISTS idx_fbpq_query       ON fb_post_queries(query);
```

---

## Qué implementar

### 1. `backend/nodes/fb_cache.py` (nuevo)

Interfaz pública mínima:

```python
async def save(page_id: str, query: str, posts: list[dict]) -> None:
    """
    Upsert de posts. Por cada post:
    - INSERT OR IGNORE en fb_posts (url, page_id, text, image_url, first_seen, last_seen)
    - UPDATE fb_posts SET text = ? WHERE url = ? AND length(?) > length(text)  (texto más largo gana)
    - UPDATE fb_posts SET last_seen = now WHERE url = ?
    - INSERT OR IGNORE en fb_post_queries (url, query, found_at)  ← UNIQUE previene duplicados
    """

async def get_all(page_id: str) -> list[dict]:
    """
    Retorna todos los posts de una página con sus queries.
    JOIN fb_posts ← fb_post_queries, agrupado por url.
    Cada dict: {url, text, image_url, queries: list[str], first_seen, last_seen}
    """

async def get_by_query(page_id: str, query: str) -> list[dict]:
    """
    Retorna posts que alguna vez salieron para esa query.
    Útil para responder: "dame todo lo que sé sobre 'perro perdido'"
    """
```

**Nota sobre `_DB_PATH`:** hacerlo configurable via variable de módulo patcheable
(como en el código actual) para que los tests puedan usar DB temporal.

```python
_DB_PATH = Path(os.getenv("FB_CACHE_DB", str(Path(__file__).parent.parent.parent / "data" / "messages.db")))
```

### 2. Fix en `fetch_facebook.py`: URL extraction

Reemplazar `_extract_post_urls` (el approach de "Compartir → Copiar enlace") por una
búsqueda de links de timestamp dentro de cada `[role="article"]`.

En Facebook, el timestamp de cada post es un `<a href>` que apunta al permalink.
Los patterns a buscar dentro de cada article:

```python
_POST_URL_PATTERNS = ("/posts/", "/permalink.php", "/share/p/")
```

Nuevo flujo en `_search_and_scrape`:

```
1. Navegar a search URL
2. Esperar feed, scroll para cargar más posts (3-4 scrolls de 600px)
3. Colectar [role="article"] del feed
4. Para cada article: buscar <a href> con patterns de permalink → extraer primera URL válida
5. Para cada URL: llamar _scrape_post_page(ctx, url) → obtener {text, image_url}
6. Retornar lista de {url, text, image_url} (solo los que tienen url real)
```

Si en un article no se encuentra ningún link válido → descartar ese article.
**Nunca usar URL de fallback tipo `fb/{page_id}`.**

### 3. Eliminar cache de `fetch_facebook.py`

Remover:
- `_DB_PATH` (se moverá a fb_cache.py)
- `_table_ready`
- `_ensure_table()`
- `_save_posts()`
- `get_cached_posts()`
- El bloque `try: await _save_posts(...)` dentro de `fetch_posts()`

`fetch_posts()` queda como estaba originalmente: solo scraping + cache en memoria.

### 4. Actualizar `graphs/luganense.py`: `buscar_posts_fb`

```python
async def buscar_posts_fb(state):
    from nodes import fetch_facebook, fb_cache

    bot_id = state.get("bot_id", "luganense")
    queries = state.get("queries") or [state["message"]]

    results = await asyncio.gather(*[
        fetch_facebook.fetch_posts(bot_id, q) for q in queries
    ])

    # Persistir en cache
    for q, posts in zip(queries, results):
        scraped = [p for p in posts if p.get("url") and "share/p" in p["url"]]
        await fb_cache.save(bot_id, q, scraped)

    # Deduplicar para el reply (comportamiento actual)
    seen = set()
    fb_posts = []
    for posts in results:
        for post in posts:
            key = post["text"][:100]
            if key not in seen:
                seen.add(key)
                fb_posts.append(post)

    fb_context = "\n\n".join(p["text"] for p in fb_posts if p["text"])
    return {"fb_posts": fb_posts, "fb_context": fb_context}
```

### 5. Migración de datos

La tabla actual `fb_posts` tiene una columna `queries TEXT` (JSON array).
El nuevo schema usa `fb_post_queries` separada.

Al crear las tablas nuevas, migrar los datos viejos:

```python
async def _migrate_legacy():
    """Migra datos de fb_posts.queries (JSON) a fb_post_queries."""
    async with aiosqlite.connect(_DB_PATH) as db:
        # Verificar si existe la columna queries (formato viejo)
        async with db.execute("PRAGMA table_info(fb_posts)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "queries" not in cols:
            return  # ya migrado o tabla nueva

        async with db.execute("SELECT url, queries FROM fb_posts WHERE queries != '[]'") as cur:
            rows = await cur.fetchall()

        now = time.time()
        for url, queries_json in rows:
            try:
                queries = json.loads(queries_json)
                for q in queries:
                    await db.execute(
                        "INSERT OR IGNORE INTO fb_post_queries (url, query, found_at) VALUES (?, ?, ?)",
                        (url, q, now)
                    )
            except Exception:
                pass

        # Eliminar columna queries de fb_posts (SQLite no soporta DROP COLUMN antes de 3.35)
        # Recrear la tabla sin esa columna
        await db.execute("ALTER TABLE fb_posts RENAME TO fb_posts_old")
        await db.execute("""
            CREATE TABLE fb_posts (
                url TEXT PRIMARY KEY, page_id TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '',
                first_seen REAL NOT NULL, last_seen REAL NOT NULL
            )
        """)
        await db.execute("""
            INSERT INTO fb_posts SELECT url, page_id, text, image_url, first_seen, last_seen
            FROM fb_posts_old
        """)
        await db.execute("DROP TABLE fb_posts_old")
        await db.commit()
```

---

## Tests a escribir

### `backend/tests/test_fb_cache.py` (reemplazar el actual)

Tests unitarios para `fb_cache.py` usando temp DB (monkeypatch `fb_cache._DB_PATH`):

| Test | Qué verifica |
|------|-------------|
| `test_save_nuevo_post` | post nuevo se inserta correctamente |
| `test_save_no_duplica_url` | misma URL × 2 → 1 fila en fb_posts |
| `test_query_no_se_duplica` | misma (url, query) × 2 → 1 fila en fb_post_queries |
| `test_acumula_queries_distintas` | (url, q1) + (url, q2) → 2 filas en fb_post_queries |
| `test_texto_mas_largo_gana` | segundo save con texto más largo → se actualiza |
| `test_texto_largo_no_se_pisa` | segundo save con texto más corto → no cambia |
| `test_get_all_incluye_queries` | get_all devuelve queries list por post |
| `test_get_by_query` | filtra correctamente por query |
| `test_filtra_por_page_id` | dos pages_id distintos no se mezclan |
| `test_posts_sin_url_se_ignoran` | URL vacía o None no se guarda |

### `scripts/test_fb_debug.py` (actualizar)

Mostrar tablas `fb_posts` y `fb_post_queries` por separado.
Verificaciones al final:
- Todos los posts en cache tienen URL con `/share/p/` o `/posts/` — ningún `fb/luganense`
- Hay al menos un post que aparece en dos queries distintas (proof: 1 fila en fb_posts, 2 en fb_post_queries)
- Links son clickeables (verificar format válido)

---

## Criterios de "done"

1. `pytest backend/tests/test_fb_cache.py` — verde ✓
2. `pytest backend/tests/test_fetch_facebook_urls.py backend/tests/test_fetch_facebook_logs.py` — verde ✓ (no regresiones)
3. `python scripts/test_fb_debug.py` con 3+ queries distintas:
   - Ningún post en cache tiene URL `https://www.facebook.com/luganense` (el fallback)
   - Al menos un post aparece en dos queries
   - Cada URL en la cache, al abrirla en browser, lleva al post específico
4. Que correr el script dos veces con las mismas queries no duplique filas (idempotente)

---

## Archivos a tocar

| Archivo | Qué hacer |
|---------|-----------|
| `backend/nodes/fb_cache.py` | CREAR — toda la lógica de persistencia |
| `backend/nodes/fetch_facebook.py` | LIMPIAR — sacar todo el código de cache; fix URL extraction |
| `backend/graphs/luganense.py` | ACTUALIZAR — `buscar_posts_fb` llama a `fb_cache.save()` |
| `backend/tests/test_fb_cache.py` | REEMPLAZAR — adaptar al nuevo módulo y schema |
| `scripts/test_fb_debug.py` | ACTUALIZAR — mostrar tablas separadas, verificaciones |

## No tocar

- `backend/graphs/luganense.py` el resto (scope_router, expandir_consulta, etc.)
- `backend/tests/test_fetch_facebook_logs.py` — tests de logging, no deben romperse
- `backend/tests/test_fetch_facebook_urls.py` — tests de URL structure, no deben romperse
- Cualquier otro test existente

---

## Notas de scraping (aprendizajes de esta sesión)

- El numeric_id de luganense es `100070998865103` — la URL de búsqueda directa funciona bien
- `_scrape_search_feed` extrae 23-47 líneas del feed de búsqueda correctamente
- El approach de "Compartir → Copiar enlace" extrae URLs del tráfico de red — funciona para
  algunos posts pero falla muchos. El approach de timestamp links es más robusto.
- FB_DEBUG=1 → browser visible + screenshots en `data/debug/` + pausa 60s al final
- Las cookies están en `data/sessions/fb-luganense/cookies.json` y son válidas actualmente
- `_scrape_post_page(ctx, url)` ya existe y funciona: navega al post, expande "Ver más", extrae texto
- La pausa de 60s en `_load_posts` con FB_DEBUG está bien — da tiempo para inspeccionar
