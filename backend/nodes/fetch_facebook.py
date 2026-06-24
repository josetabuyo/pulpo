"""
Node: fetch_facebook

Scrapea los posts recientes de una página pública de Facebook usando Playwright.
Requiere una cuenta FB con acceso (FB_EMAIL + FB_PASSWORD en .env).

Login: la primera vez (o cuando las cookies expiran) abre un browser VISIBLE para
       evitar la detección anti-bot de Facebook. El usuario puede ver el proceso.
       Las cookies se guardan en data/sessions/fb-{page_id}/cookies.json.

Scraping: usa browser headless con las cookies guardadas. Cachea 30 min.

Interfaz pública:
  fetch_posts(page_id, query) -> list[dict]  — posts con {text, image_url}
  fetch(page_id, query)       -> str         — texto combinado (compat. con tests)
  invalidate(page_id)                        — fuerza re-scraping

Interfaz futura: cuando haya Graph API key, se reemplaza _load_posts() sin tocar el grafo.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_TTL = 30 * 60       # 30 minutos
_MAX_POSTS = 8
_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"

# Lock global para evitar múltiples logins simultáneos cuando las cookies expiran
_login_lock = asyncio.Lock()

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

# Segundos que el browser visible permanece abierto cuando FB muestra algo sospechoso,
# para que el usuario pueda leer el cartel antes de que se cierre.
_PAUSE_ON_SUSPICIOUS = 90

_SUSPICIOUS_URL_FRAGMENTS = ("login", "checkpoint", "index.php", "recover", "secure", "suspended", "hacked")

# cache en memoria: "page_id:query" -> (timestamp, list[dict])
_posts_cache: dict[str, tuple[float, list[dict]]] = {}


# ─── Interfaz pública ────────────────────────────────────────────────────────

async def fetch_posts(page_id: str, query: str = "", numeric_id: str = "") -> list[dict]:
    """
    Retorna lista de posts: [{"text": str, "image_url": str}].
    - page_id:    slug de la página FB (ej: "luganense", "cnn")
    - numeric_id: ID numérico (opcional) — habilita búsqueda directa dentro de la página
    Los posts estáticos (solo para páginas configuradas) se incluyen al principio.
    Cachea 30 min por (page_id, query).
    """
    cache_key = f"{page_id}:{query}"
    cached = _posts_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        logger.debug("[fetch_facebook] cache hit — %s", cache_key)
        return cached[1]

    # numeric_id: el parámetro tiene precedencia, luego el diccionario hardcodeado
    resolved_numeric_id = numeric_id or _PAGE_NUMERIC_IDS.get(page_id, "")

    scraped = await _load_posts(page_id, query, resolved_numeric_id)

    # Posts estáticos: solo se agregan cuando hay query Y scraped tiene resultados,
    # o cuando no hay query (browsing del feed general).
    # Si la búsqueda no encontró nada, no contaminar con static posts irrelevantes.
    if scraped or not query:
        static_posts = _STATIC_POSTS.get(page_id, [])
        static_dicts = [{"text": sp, "image_url": ""} for sp in static_posts]
        for i, sp in enumerate(static_dicts):
            logger.info("[fetch_facebook] static %d: %s", i + 1, sp["text"][:80].replace('\n', ' '))
        posts = static_dicts + scraped
    else:
        posts = []

    if posts:
        _posts_cache[cache_key] = (time.time(), posts)
    return posts


async def fetch(page_id: str, query: str = "", numeric_id: str = "") -> str:
    """Texto combinado de todos los posts. Compatibilidad con código existente."""
    posts = await fetch_posts(page_id, query, numeric_id)
    return "\n\n".join(p["text"] for p in posts if p["text"])


def invalidate(page_id: str) -> None:
    """Fuerza re-scraping en el próximo fetch."""
    keys = [k for k in _posts_cache if k.startswith(f"{page_id}:")]
    for k in keys:
        del _posts_cache[k]
    logger.info("[fetch_facebook] cache invalidada para '%s'", page_id)


# ─── Implementación interna ──────────────────────────────────────────────────

async def _load_posts(page_id: str, query: str, numeric_id: str = "") -> list[dict]:
    """Scrapea FB y retorna posts estructurados. Sin cache ni posts estáticos."""
    from playwright.async_api import async_playwright

    email = os.getenv("FB_EMAIL", "").strip()
    password = os.getenv("FB_PASSWORD", "").strip()
    if not email or not password:
        logger.error("[fetch_facebook] FB_EMAIL / FB_PASSWORD no configurados")
        return []

    cookies_path = _SESSIONS_DIR / f"fb-{page_id}" / "cookies.json"
    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    if not cookies_path.exists():
        async with _login_lock:
            # Re-check dentro del lock: otra coroutine puede haber completado el login
            if not cookies_path.exists():
                logger.info("[fetch_facebook] Sin cookies → login con browser visible...")
                ok = await _do_login_visible(email, password, cookies_path)
                if not ok:
                    return []

    async with async_playwright() as pw:
        headless = not os.getenv("FB_DEBUG")
        # Viewport retrato y alto — misma estrategia que wavi: maximiza contenido
        # visible por posición de scroll. 1280×4096 encaja un feed de ~8-12 posts
        # sin necesidad de scroll. device_scale_factor=0.5 = zoom alejado al 50%.
        browser = await pw.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            locale="es-AR",
            user_agent=_UA,
            viewport={"width": 1280, "height": 4096},
            device_scale_factor=0.5,
        )

        try:
            saved = json.loads(cookies_path.read_text())
            await ctx.add_cookies(saved)
            logger.info("[fetch_facebook] Cookies cargadas desde disco")
        except Exception as e:
            logger.warning("[fetch_facebook] Error cargando cookies: %s", e)

        page = await ctx.new_page()
        await page.goto(
            f"https://www.facebook.com/{page_id}/posts",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(2_500)

        if "login" in page.url or "checkpoint" in page.url:
            logger.warning("[fetch_facebook] Sesión expirada — cookies eliminadas, re-login requerido")
            cookies_path.unlink(missing_ok=True)
            await browser.close()
            return []

        if query:
            posts = await _search_and_scrape(page, query, page_id, numeric_id)
        else:
            posts = await _scrape_posts(page, page_id)

        if os.getenv("FB_DEBUG"):
            logger.info("[fetch_facebook] FB_DEBUG: pausa 60s — inspeccioná el browser antes de cerrar")
            await page.wait_for_timeout(60_000)

        await browser.close()

    if not posts:
        logger.warning("[fetch_facebook] No se encontraron posts para '%s'", page_id)
        return []

    logger.info("[fetch_facebook] %d posts extraídos para '%s'", len(posts), page_id)
    return posts


async def _do_login_visible(email: str, password: str, cookies_path: Path) -> bool:
    """Abre browser VISIBLE para login en Facebook. Guarda cookies en cookies_path."""
    import asyncio as _asyncio
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            ctx = await browser.new_context(locale="es-AR", user_agent=_UA)
            page = await ctx.new_page()

            await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(1_500)
            await page.wait_for_selector("input[name='email']", timeout=15_000)
            await page.fill("input[name='email']", email)
            await page.fill("input[name='pass']", password)
            await page.press("input[name='pass']", "Enter")

            # Esperar sin límite a que aparezca c_user
            tick = 0
            while True:
                cookies = await ctx.cookies()
                if any(c["name"] == "c_user" for c in cookies):
                    break
                await _asyncio.sleep(1)
                tick += 1
                if tick % 30 == 0:
                    logger.info("[fetch_facebook] login visible: esperando c_user (%ds)...", tick)

            # Intentar cerrar el aviso de "comportamiento automatizado" si aparece
            try:
                await page.get_by_text("Descartar", exact=True).click(timeout=5_000)
                logger.info("[fetch_facebook] Aviso de Facebook cerrado automáticamente (botón Descartar).")
            except Exception:
                pass  # el aviso no apareció, seguir normal

            # Guardar cookies inmediatamente
            cookies_path.write_text(json.dumps(cookies, ensure_ascii=False))
            logger.info("[fetch_facebook] Login exitoso — cookies guardadas en %s.", cookies_path)
            logger.info("[fetch_facebook] ⚠️  MIRÁ EL BROWSER: ¿Facebook muestra algún aviso o advertencia? Esperando 30s mínimo.")

            # Espera mínima para que el usuario pueda leer mensajes de FB
            for i in range(30, 0, -1):
                logger.info("[fetch_facebook] Cerrando browser en %ds...", i)
                await _asyncio.sleep(1)

            # Esperar a que el usuario cierre el browser
            logger.info("[fetch_facebook] Tiempo mínimo cumplido. Cerrá el browser cuando quieras.")
            while browser.is_connected():
                await _asyncio.sleep(1)

            return True

    except Exception as e:
        logger.error("[fetch_facebook] Excepción en login visible: %s", e)
        return False


async def _scrape_post_page(ctx, url: str) -> dict:
    """
    Navega a un post individual.
    Retorna {"text": str, "image_url": str}.
    Captura og:image del <meta> del post.
    """
    try:
        post_page = await ctx.new_page()
        await post_page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        await post_page.wait_for_timeout(2_000)

        # Capturar og:image
        image_url = ""
        try:
            meta = await post_page.query_selector("meta[property='og:image']")
            if meta:
                image_url = await meta.get_attribute("content") or ""
                if image_url:
                    logger.info("[fetch_facebook] og:image: %s", image_url[:60])
        except Exception as e:
            logger.debug("[fetch_facebook] sin og:image: %s", e)

        # Texto: og:description es la fuente más confiable (FB lo inyecta por JS).
        # Esperar hasta 4s a que aparezca antes de caer al body fallback.
        raw = ""
        try:
            await post_page.wait_for_selector(
                "meta[property='og:description']", timeout=4_000
            )
            meta_desc = await post_page.query_selector("meta[property='og:description']")
            if meta_desc:
                raw = await meta_desc.get_attribute("content") or ""
                if raw:
                    logger.debug("[fetch_facebook] og:description: %s", raw[:80])
        except Exception:
            pass

        if len(raw.strip()) < 30:
            raw = await post_page.inner_text("body")

        await post_page.close()

        lines = [
            l.strip() for l in raw.split("\n")
            if len(l.strip()) > 10
            and l.strip() not in _UI_NOISE
            and not l.strip().startswith("0:0")
            and not any(noise in l for noise in _BODY_NOISE)
        ]
        text = "\n".join(lines[:40]) if lines else ""
        return {"text": text, "image_url": image_url, "url": url}

    except Exception as e:
        logger.warning("[fetch_facebook] Error scraping post %s: %s", url, e)
        return {"text": "", "image_url": "", "url": url}


_PERMALINK_PATTERNS_JS = ("/posts/", "/permalink.php", "/share/p/", "/story.php")


async def _extract_feed_urls(page, max_posts: int = 5, numeric_id: str = "") -> list[str]:
    """
    Extrae URLs de posts haciendo un único page.evaluate() que escanea todo el DOM.
    a.href resuelve URLs absolutas — maneja relativos y encoding de Facebook.
    """
    if os.getenv("FB_DEBUG"):
        try:
            all_page_hrefs = await page.evaluate("""() => {
                const hrefs = [];
                for (const a of document.querySelectorAll('a[href]')) {
                    const h = a.href;
                    if (h && !h.startsWith('javascript') && h !== window.location.href)
                        hrefs.push(h);
                }
                return [...new Set(hrefs)].slice(0, 60);
            }""")
            logger.info("[fetch_facebook] FB_DEBUG: %d hrefs únicos en página", len(all_page_hrefs))
            for h in all_page_hrefs:
                logger.info("[fetch_facebook] href: %s", h[:120])
        except Exception as e:
            logger.debug("[fetch_facebook] FB_DEBUG href scan error: %s", e)

    patterns = list(_PERMALINK_PATTERNS_JS)
    try:
        urls = await page.evaluate("""([patterns, numericId]) => {
            const seen = new Set();
            const result = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                if (!href || href === window.location.href) continue;

                // Todas las fotos (set=pcb.POST_ID o set=a.ALBUM_ID): usar photo?fbid=
                // og:description en la página de foto contiene el caption del post completo.
                // permalink.php?story_fbid= no popula og:description en vista autenticada.
                if (href.includes('/photo/') && href.includes('fbid=')) {
                    const m = href.match(/fbid=([0-9]+)/);
                    if (m) {
                        const photoUrl = 'https://www.facebook.com/photo?fbid=' + m[1];
                        if (!seen.has(photoUrl)) { seen.add(photoUrl); result.push(photoUrl); }
                    }
                    continue;
                }

                // Posts con permalink directo (/posts/, /share/p/, etc.)
                if (patterns.some(p => href.includes(p))) {
                    const base = href.split('?')[0];
                    if (!seen.has(base)) { seen.add(base); result.push(base); }
                }
            }
            return result;
        }""", [patterns, numeric_id])
        logger.info("[fetch_facebook] feed scan: %d URLs encontradas", len(urls))
        for u in urls[:max_posts]:
            logger.info("[fetch_facebook] feed URL: %s", u)
        return urls[:max_posts]
    except Exception as e:
        logger.warning("[fetch_facebook] Error en feed scan: %s", e)
        return []


async def _extract_feed_urls_sorted(page, numeric_id: str = "") -> list[str]:
    """
    Como _extract_feed_urls pero retorna URLs ordenadas por posición vertical (getBoundingClientRect.top).
    Permite identificar el último post visible para anclar el scroll entre rondas.
    """
    patterns = list(_PERMALINK_PATTERNS_JS)
    try:
        items = await page.evaluate("""([patterns]) => {
            const seen = new Set();
            const result = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                if (!href || href === window.location.href) continue;

                let url = null;
                if (href.includes('/photo/') && href.includes('fbid=')) {
                    const m = href.match(/fbid=([0-9]+)/);
                    if (m) url = 'https://www.facebook.com/photo?fbid=' + m[1];
                } else if (patterns.some(p => href.includes(p))) {
                    url = href.split('?')[0];
                }

                if (url && !seen.has(url)) {
                    seen.add(url);
                    const rect = a.getBoundingClientRect();
                    result.push({ url, top: rect.top });
                }
            }
            result.sort((a, b) => a.top - b.top);
            return result.map(r => r.url);
        }""", [patterns])
        return items
    except Exception as e:
        logger.warning("[fetch_facebook] Error en feed scan ordenado: %s", e)
        return []


async def _search_and_scrape(page, query: str, page_id: str = "", numeric_id: str = "") -> list[dict]:
    """
    Navega a la URL de búsqueda directa de la página.
    Fallback: scraping del feed con seeds si la búsqueda no rinde resultados.
    Retorna list[{text, image_url}].
    """
    import urllib.parse

    if numeric_id:
        try:
            search_url = (
                f"https://www.facebook.com/profile/{numeric_id}/search"
                f"?q={urllib.parse.quote(query)}"
            )
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(5_000)

            if "login" in page.url or "checkpoint" in page.url or "index.php" in page.url:
                logger.warning("[fetch_facebook] Sesión expirada en búsqueda — cookies eliminadas, re-login requerido")
                cookies_path = _SESSIONS_DIR / f"fb-{page_id}" / "cookies.json"
                cookies_path.unlink(missing_ok=True)
                return []

            logger.info("[fetch_facebook] Búsqueda directa: '%s' → %s", query, search_url)

            if os.getenv("FB_DEBUG"):
                debug_dir = Path(__file__).parent.parent.parent / "data" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                await page.screenshot(
                    path=str(debug_dir / f"fb_search_{page_id}_{query[:20].replace(' ', '_')}.png"),
                    full_page=False,
                )

            # Viewport grande para maximizar posts visibles por ronda
            original_vp = page.viewport_size or {"width": 1280, "height": 800}
            await page.set_viewport_size({"width": 1280, "height": 2400})
            await page.wait_for_timeout(800)

            # Scroll con ancla: acumula globalmente, avanza hasta que el último
            # post visible quede arriba (evita perder posts por virtualización del DOM)
            MAX_ROUNDS = 25
            MAX_POSTS = 30
            all_seen: set[str] = set()
            post_urls: list[str] = []
            dry_rounds = 0

            try:
                for _ in range(MAX_ROUNDS):
                    batch = await _extract_feed_urls_sorted(page, numeric_id=numeric_id)

                    new_in_batch = [u for u in batch if u not in all_seen]
                    for u in new_in_batch:
                        all_seen.add(u)
                        post_urls.append(u)

                    logger.info(
                        "[fetch_facebook] scroll round: +%d nuevos, %d acumulados",
                        len(new_in_batch), len(post_urls),
                    )

                    if len(post_urls) >= MAX_POSTS:
                        break

                    if not new_in_batch:
                        dry_rounds += 1
                        if dry_rounds >= 3:
                            break
                    else:
                        dry_rounds = 0

                    if not batch:
                        break

                    # Ancla: scrollear hasta que el último post visible quede arriba,
                    # luego empujar un viewport más para saltar el área ya vista y
                    # activar el lazy loading de FB con contenido nuevo abajo.
                    last_url = batch[-1]
                    scrolled = await page.evaluate("""(lastUrl) => {
                        const patterns = ['/photo/', '/posts/', '/permalink.php', '/share/p/', '/story.php'];
                        for (const a of document.querySelectorAll('a[href]')) {
                            const href = a.href;
                            let url = null;
                            if (href.includes('/photo/') && href.includes('fbid=')) {
                                const m = href.match(/fbid=([0-9]+)/);
                                if (m) url = 'https://www.facebook.com/photo?fbid=' + m[1];
                            } else if (patterns.some(p => href.includes(p))) {
                                url = href.split('?')[0];
                            }
                            if (url === lastUrl) {
                                a.scrollIntoView({ block: 'start', behavior: 'instant' });
                                return true;
                            }
                        }
                        return false;
                    }""", last_url)

                    if not scrolled:
                        # Fallback: saltar un viewport completo desde posición actual
                        await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    else:
                        # Ancla posicionó el último post arriba → empujar para saltar el área ya vista
                        await page.evaluate("window.scrollBy(0, window.innerHeight)")

                    await page.wait_for_timeout(2_500)
            finally:
                await page.set_viewport_size(original_vp)

            post_urls = post_urls[:MAX_POSTS]
            if not post_urls:
                logger.info("[fetch_facebook] Sin URLs de posts para query '%s'", query)
                return []

            ctx = page.context
            posts = []
            for url in post_urls:
                post = await _scrape_post_page(ctx, url)
                if post.get("text"):
                    posts.append(post)
                    logger.info("[fetch_facebook] post %d: %s", len(posts), post["text"][:80].replace('\n', ' '))

            logger.info("[fetch_facebook] Búsqueda: %d posts para '%s'", len(posts), query)
            return posts
        except Exception as e:
            err_str = str(e)
            if "ERR_TOO_MANY_REDIRECTS" in err_str or "net::ERR_" in err_str:
                logger.warning("[fetch_facebook] Sesión expirada (redirect loop) — cookies eliminadas, re-login requerido")
                cookies_path = _SESSIONS_DIR / f"fb-{page_id}" / "cookies.json"
                cookies_path.unlink(missing_ok=True)
            else:
                logger.warning("[fetch_facebook] Error en búsqueda directa: %s", e)
            return []
    else:
        logger.info("[fetch_facebook] Sin ID numérico para '%s', usando feed", page_id)

    return await _scrape_posts(page, page_id)


async def _scrape_posts(page, page_id: str = "") -> list[dict]:
    """
    Recolecta URLs de posts del perfil, navega a cada uno y extrae texto + imagen.
    Retorna list[{text, image_url}].
    """
    urls = await _collect_post_urls(page, page_id)
    if not urls:
        logger.warning("[fetch_facebook] No se encontraron URLs de posts")
        return []

    ctx = page.context
    posts = []
    for url in urls:
        post = await _scrape_post_page(ctx, url)
        if post["text"]:
            posts.append(post)
            logger.info("[fetch_facebook] post %d: %s", len(posts), post["text"][:80].replace('\n', ' '))

    return posts


async def _collect_post_urls(page, page_id: str) -> list[str]:
    """
    Recolecta URLs de posts individuales.
    Prioridad: seeds hardcodeados → links del feed headless.
    """
    urls: list[str] = []
    seen: set[str] = set()

    for seed in _SEED_URLS.get(page_id, []):
        base = seed.split("?")[0]
        if base not in seen:
            seen.add(base)
            urls.append(base)

    for _ in range(4):
        await page.evaluate("window.scrollBy(0, 800)")
        await page.wait_for_timeout(1_500)

    try:
        links = await page.query_selector_all("a[href]")
        for link in links:
            href = await link.get_attribute("href") or ""
            if not any(p in href for p in _POST_URL_PATTERNS):
                continue
            if href.startswith("/"):
                href = f"https://www.facebook.com{href}"
            base = href.split("?")[0]
            if base not in seen:
                seen.add(base)
                urls.append(base)
    except Exception as e:
        logger.error("[fetch_facebook] Error recolectando URLs: %s", e)

    logger.info("[fetch_facebook] %d URLs de posts encontradas", len(urls))
    return urls[:_MAX_POSTS]


# ─── Datos de configuración por página ──────────────────────────────────────

_SEED_URLS: dict[str, list[str]] = {
    "luganense": [
        "https://www.facebook.com/luganense/posts/pfbid0UYq8USWM2BtCxJEC6wK9yzf5T226iG8mqnHGWxWR19z6JaAnQkiQLyBUUTGYYCPYl",
        "https://www.facebook.com/luganense/posts/pfbid0y3qNc2B6pqN3d9HHTpNwT8c7JoxKj6AMcTH7kEj7UTkQL59r7h3drAHg5Pg8hSMil",
        "https://www.facebook.com/luganense/posts/pfbid0ztrskdpEdKwrisPNv5eppiqa6j921H5b8mr7aEW1LqEkh2YsDZQHbf5nqFAfKBRgl",
        "https://www.facebook.com/luganense/posts/pfbid02ybisUk22dqo5e8Pfwdo2wJYUjDtYReNrNBWKnjbhiNiy1HJNYUaX9ii9Rz88HDcxl",
        "https://www.facebook.com/luganense/posts/pfbid02eMA9gfcEz67bbpxu9t51zdWN2nqet8KATynjaqUxc5oUJ5Hc79Uo61kfZLaY5CVDl",
    ]
}

_PAGE_NUMERIC_IDS: dict[str, str] = {
    "luganense": "100070998865103",
}

_STATIC_POSTS: dict[str, list[str]] = {
    "luganense": [
        (
            "🔥 ¡ATENCIÓN VILLA LUGANO!\n"
            "🍗 ¡Llegó una nueva pollería peruana al barrio… y viene con OFERTAS de inauguración!\n"
            "Este 14 de marzo abre sus puertas \"Sabor Peruano\", un nuevo restaurante–pollería en Villa Lugano.\n"
            "👉 PROMO DE INAUGURACIÓN:\n"
            "🍗 Pollo entero + papas + ensalada + cremas\n"
            "🍚 Arroz chaufa o chola de oro\n"
            "💰 $25.000\n"
            "🔥 Oferta especial: POLLO BROASTER 3x2\n"
            "📍 Dirección: Larraya 4258 (Pje. Hebe San Martín de Duprat)\n"
            "🕚 Horario: de 11 a 23 hs\n"
            "🚚 Envíos desde el lunes\n"
            "💳 Efectivo y Mercado Pago\n"
            "📲 Pedidos: 11 2323-2427\n"
            "🥢 En el menú también vas a encontrar:\n"
            "✔ Arroz chaufa ✔ Lomo saltado ✔ Tallarín saltado ✔ Mostrito ✔ Salchipapas "
            "✔ Milanesa ✔ Lomito / Bife ✔ ¡Y más menú variado!\n"
            "❤️ Vecinos de Villa Lugano, Lugano 1 y 2, Piedrabuena, Samoré y Nagera: "
            "¡Una nueva opción gastronómica llega al barrio!"
        ),
    ],
}

_UI_NOISE = {
    "Me gusta", "Comentar", "Compartir", "Ver más", "Luganense",
    "Todo", "Publicaciones", "Información", "Fotos", "Seguidores", "Menciones",
    "Reels", "Grupos", "Marketplace", "Todas las reacciones:",
    "Iniciar sesión", "¿Olvidaste la cuenta?", "¿Olvidaste tu contraseña?",
    "Ve más en Facebook", "Crear cuenta nueva", "Audio original",
    "Correo electrónico o número de teléfono", "Contraseña",
    "Indicador de estado online", "Activo", "Facebook",
    "Comentarios",  # encabezado de sección de comentarios en FB
}

# Substrings que indican basura del body de FB (navegación, UI vacía, etc.)
_BODY_NOISE = (
    "Audio original",
    "chats no leídos",
    "notificaciones no leídas",
    "Esta foto es de una publicación",
    "Fan destacado",
    "Todavía no hay comentarios",
    "Sé la primera persona en comentar",
    "Escribe un comentario",
    "Ver publicación",
    "Menú de Facebook",
    "Tus accesos directos",
    "Candy Crush",
    "days ago", "hours ago", "minutes ago",  # timestamps en inglés = página de FB autenticada
)

_POST_URL_PATTERNS = ("/posts/", "/photo.php", "/reel/", "/videos/")
