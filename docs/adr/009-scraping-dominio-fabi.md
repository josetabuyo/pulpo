# ADR-009: El scraping de Facebook pasa a ser dominio de Fabi

**Estado:** Aceptado — julio 2026. **Parcialmente superado por
[ADR-011](011-fetch-fb-eliminado-todo-via-fetch-http.md)** (vía
[ADR-010](010-noticias-http-directo-a-luganense.md), ya superado del todo) —
la parte de "el scraping en sí es dominio de Fabi" (§1, §2, §5 de abajo) sigue
vigente; la parte de "Pulpo habla con Fabi en proceso vía `fabi_driver.py`"
(§3, §4, §6) quedó reemplazada, primero por una consulta HTTP directa vía un
cliente dedicado (ADR-010), y ese mismo día por el nodo genérico
`FetchHttpNode` sin código nuevo (ADR-011) — ver ese documento para el
estado final.

## Contexto

ADR-008 movió la *cache* de noticias (persistencia de posts ya scrapeados) a
la tabla `noticias` de Luganense, pero el *scraping en sí* — Playwright,
cookies de FB, login, anti-detección — seguía viviendo dentro de Pulpo
(`pulpo/tools/facebook/fetch_facebook.py`, `scripts/fb_login.py`,
`scripts/fb_check_cookies.py`). Eso mezclaba dos responsabilidades muy
distintas bajo un mismo repo: un motor de flows conversacionales (Pulpo) y un
scraper de una red social ajena con su propio ciclo de vida de riesgo (baneo
de cuenta, rate-limiting, detección de actividad sospechosa).

Se creó un proyecto nuevo, **Fabi** (`/Users/josetabuyo/Development/Fabi`),
siguiendo el mismo patrón que `wavi` (automatización de WhatsApp Web) y
`teli` (Telegram) en este ecosistema: repo propio, agente LAS propio (voz
Paulina, es-AR), librería Python publicable (`fabi-lib`) con tres interfaces
(`cli`, `api`, `lib` — sin `ui`, no hace falta frontend) sobre un `core/`
compartido. "Conexiones" (páginas de Facebook) con alias, incluyendo
`default`, igual que las sesiones de `wavi`.

## Decisión

1. **Fabi asume todo el scraping** — login, cookies, anti-detección, extracción
   de posts (`fabi/core/scraper.py`, portado 1:1 de `fetch_facebook.py`) — y
   la persistencia local (`fabi/core/storage.py`, JSON por conexión, dedup por
   URL, reemplaza al modelo de dos tablas que tenía `fb_cache.py`).
2. **Fabi también asume el hablar con Luganense.** La inyección de posts
   nuevos a `/api/noticias` (antes `pulpo/tools/facebook/news_api.py`) ahora
   es `fabi/core/targets.py` — configurable por conexión, no hardcodeado a
   Luganense (Fabi es un servicio de scraping de Facebook en general; Luganense
   es su primer consumidor, no el único).
3. **Pulpo habla con Fabi vía `pulpo/tools/fabi_driver.py`**, wrapper delgado
   in-proceso sobre `fabi-lib` (instalado editable desde el path local — no
   está publicado a PyPI todavía, ver `pyproject.toml` `[tool.uv.sources]`).
   Mismo criterio que `pulpo/tools/wavi_driver.py`. Pulpo ya no importa
   Playwright para Facebook, no maneja cookies de FB, no sabe la URL de
   `/api/noticias`.
4. **Camino rápido / camino lento en `FetchFbNode`.** El pedido explícito era
   un flujo más rápido usando lectura directa en vez de disparar un scraping
   en cada mensaje. `FetchFbNode` ahora:
   - Primero llama `fabi_driver.posts_for(page_id, query)` — lectura contra
     el storage de Fabi, sin browser.
   - Si no hay nada, recién ahí `fabi_driver.fetch_posts(page_id, query)` —
     le pide a Fabi que scrapee (Fabi decide con su propio early-stop si hace
     falta un browser real).
   - `fb_numeric_id` deja de ser config del nodo — ahora es config de la
     conexión en Fabi (`fabi connection add --numeric-id`).
5. **Se borró todo el código de scraping propio de Pulpo**: `pulpo/tools/facebook/`
   entero (`fetch_facebook.py`, `news_api.py`), `scripts/fb_login.py`,
   `scripts/fb_check_cookies.py`. Las cookies vigentes de la cuenta de FB de
   Luganense se migraron por copia directa de archivo a Fabi (no se
   duplicaron credenciales, no se re-hizo login).
6. **Tests e2e migrados, no borrados.** `tests/e2e/luganense/test_noticias_persistencia.py`
   ahora prueba el límite de responsabilidad real de Pulpo (`fabi_driver`
   hablando con la librería real de Fabi), no el contrato HTTP con Luganense
   — eso es responsabilidad de Fabi y tiene su propia suite ahí.
   `test_ruta_noticias` (flow completo vía Telegram) no cambió.

## Consecuencias

- Pulpo ya no puede romper una sesión de Facebook por accidente — ese riesgo
  vive aislado en Fabi, con su propio ciclo de testing y logs.
- Nuevo acoplamiento: Pulpo depende de que `fabi-lib` esté instalado editable
  desde un path local (`../../Fabi` relativo a `pulpo/_/`). Si algún día se
  publica a PyPI (mismo flujo que `wavi-lib`/`teli-lib`), cambiar a un pin de
  versión normal en `[project.dependencies]` y borrar `[tool.uv.sources]`.
- Si Fabi cambia la forma de `posts_for()`/`scrape()` (el contrato que expone
  `fabi.interfaces.lib.FabiClient`), `fabi_driver.py` es el único lugar de
  Pulpo que hay que tocar — `FetchFbNode` no sabe nada de Fabi directamente.
- **Pendiente, otra sesión (explícitamente fuera de alcance acá):** convertir
  la rama de noticias del flow en una conversación real multi-turno (hoy
  responde una vez y cierra) — ver `management/HANDOFF_FABI_SCRAPER.md` §4.
