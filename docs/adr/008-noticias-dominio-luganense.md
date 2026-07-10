# ADR-008: La tabla de noticias pasa a ser dominio de Luganense

**Estado:** Aceptado — julio 2026. **Superado por [ADR-009](009-scraping-dominio-fabi.md)**
(el scraping en sí, no solo la cache, se movió a un servicio propio, Fabi).
Este documento queda como registro histórico de la decisión original — no
reescribir, el contexto de abajo fue real y vigente en su momento.

## Contexto

Luganense (el cliente) montó su propia infraestructura (Next.js + Neon,
repo separado `Luganense/`) para directorio de comercios/productos/servicios,
con endpoints públicos que Pulpo ya consume (`/api/directorio/buscar`) y
alimenta (`/api/metricas`, POST público sin auth).

Hasta ahora, el nodo `Buscar Facebook` (`FetchFbNode` → `fetch_facebook.py`)
scrapeaba posts de la página de FB de Luganense y los cacheaba en
`pulpo/tools/facebook/fb_cache.py`, una tabla SQLite local en `data/messages.db`
(`fb_posts` + `fb_post_queries`). Esa cache era responsabilidad nuestra pero
conceptualmente es dato de dominio de Luganense — noticias del barrio — igual
que sus comercios y productos.

Auditoría al armar esta migración encontró que `fb_cache._DB_PATH` calculaba
mal su ruta default (`pulpo/data/messages.db`, un nivel de más desde el
reorg de ADR-001) — apuntaba a un archivo que no existía. La cache local
llevaba tiempo sin persistir nada nuevo silenciosamente; los 64 posts que
tenía databan de antes de ese reorg.

## Decisión

1. **La tabla de noticias es de Luganense.** Agregaron `noticias` (Neon/Drizzle)
   + dos endpoints en su repo:
   - `POST /api/noticias` — público (mismo criterio que `/api/metricas`), lo
     llama Pulpo con `{page_id, query, posts:[{url,text,image_url}]}`, upsert
     por `url`.
   - `GET /api/noticias?page_id=...&q=...&max_age=...` — público (mismo
     criterio que `/api/directorio/buscar`), devuelve `{results, total}`.
2. **`pulpo/tools/facebook/news_api.py`** reemplaza a `fb_cache.py`: misma
   interfaz (`save`, `get_by_query`, `get_urls`), pero habla HTTP contra
   `LUGANENSE_NEWS_API_URL` (env, default `https://luganense.vercel.app/api/noticias`)
   en vez de SQLite local. `fetch_facebook.py` solo cambió el import.
3. **Fail-soft, no fail-hard.** Un error de red o 5xx de Luganense en
   `news_api.get_by_query`/`get_urls` degrada a lista vacía (se trata como
   "sin cache", vuelve a scrapear FB); un error en `save` se loguea a nivel
   ERROR pero no interrumpe el flow — mismo criterio que
   `MetricNode._notify_webhook`.
4. **`fb_cache.py` y `scripts/test_fb_debug.py` se borraron.** Los 64 posts
   locales se migraron una sola vez (script ad-hoc, no versionado) a
   `/api/noticias` antes de borrar — verificado con `GET /api/noticias`
   devolviendo `total: 64`. `test_fb_debug.py` ya estaba roto de antes
   (importaba `nodes.fb_cache` y `sys.path` a `backend/`, ninguno de los
   dos existe desde ADR-001/007) — doblemente confirmado como muerto.

## Consecuencias

- Coordinación cross-repo: cambios al contrato de `/api/noticias` los decide
  Luganense, pero deben avisarnos — si cambian de forma, `news_api.py` rompe
  en `_get`/`save` (degradado, no crash, pero sin cache funcional).
- Nada de Facebook queda persistido en `data/messages.db` — si se necesita
  historial de posts, vive en Neon del lado Luganense.
- **Pendiente, otra sesión:** dividir `FetchFbNode` en nodos más chicos
  (fetch crudo / cache / formateo). Este ADR solo cambia el backend de la
  cache, no la forma del nodo en el editor de flows.
