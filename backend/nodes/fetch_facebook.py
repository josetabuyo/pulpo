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
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_TTL = 30 * 60       # 30 minutos
_MAX_POSTS = 8
_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# cache estructurado: "page_id:query" -> (timestamp, list[dict])
_posts_cache: dict[str, tuple[float, list[dict]]] = {}


# ─── Interfaz pública ────────────────────────────────────────────────────────

async def fetch_posts(page_id: str, query: str = "") -> list[dict]:
    """
    Retorna lista de posts: [{"text": str, "image_url": str}].
    Los posts estáticos siempre se incluyen al principio.
    Cachea 30 min por (page_id, query).
    """
    cache_key = f"{page_id}:{query}"
    cached = _posts_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        logger.debug("[fetch_facebook] cache hit — %s", cache_key)
        return cached[1]

    scraped = await _load_posts(page_id, query)

    # Posts estáticos (reels y contenido no scrapeble en headless) — siempre primero
    static_posts = _STATIC_POSTS.get(page_id, [])
    static_dicts = [{"text": sp, "image_url": ""} for sp in static_posts]
    for i, sp in enumerate(static_dicts):
        logger.info("[fetch_facebook] static %d: %s", i + 1, sp["text"][:80].replace('\n', ' '))

    posts = static_dicts + scraped

    if posts:
        _posts_cache[cache_key] = (time.time(), posts)
    return posts


async def fetch(page_id: str, query: str = "") -> str:
    """Texto combinado de todos los posts. Compatibilidad con código existente."""
    posts = await fetch_posts(page_id, query)
    return "\n\n".join(p["text"] for p in posts if p["text"])


def invalidate(page_id: str) -> None:
    """Fuerza re-scraping en el próximo fetch."""
    keys = [k for k in _posts_cache if k.startswith(f"{page_id}:")]
    for k in keys:
        del _posts_cache[k]
    logger.info("[fetch_facebook] cache invalidada para '%s'", page_id)


# ─── Implementación interna ──────────────────────────────────────────────────

async def _load_posts(page_id: str, query: str) -> list[dict]:
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
        logger.info("[fetch_facebook] Sin cookies → login con browser visible...")
        ok = await _do_login_visible(email, password, cookies_path)
        if not ok:
            return []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="es-AR",
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
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
            posts = await _search_and_scrape(page, query, page_id)
        else:
            posts = await _scrape_posts(page, page_id)

        await browser.close()

    if not posts:
        logger.warning("[fetch_facebook] No se encontraron posts para '%s'", page_id)
        return []

    logger.info("[fetch_facebook] %d posts extraídos para '%s'", len(posts), page_id)
    return posts


async def _do_login_visible(email: str, password: str, cookies_path: Path) -> bool:
    """Abre browser VISIBLE para login en Facebook. Guarda cookies en cookies_path."""
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
            await page.wait_for_timeout(6_000)

            if "login" in page.url or "checkpoint" in page.url:
                logger.error("[fetch_facebook] Login falló. URL: %s", page.url)
                await browser.close()
                return False

            cookies_path.write_text(json.dumps(await ctx.cookies(), ensure_ascii=False))
            logger.info("[fetch_facebook] Login exitoso — cookies guardadas en %s", cookies_path)
            await browser.close()
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
        except Exception:
            pass

        # Expandir texto truncado
        try:
            ver_mas = await post_page.query_selector(
                "button:has-text('Ver más'), [role='button']:has-text('Ver más')"
            )
            if ver_mas:
                await ver_mas.click()
                await post_page.wait_for_timeout(800)
        except Exception:
            pass

        # Texto: article principal o body completo
        raw = ""
        articles = await post_page.query_selector_all("[role='article']")
        if articles:
            raw = await articles[0].inner_text()
        if len(raw.strip()) < 30:
            raw = await post_page.inner_text("body")

        await post_page.close()

        lines = [
            l.strip() for l in raw.split("\n")
            if len(l.strip()) > 10
            and l.strip() not in _UI_NOISE
            and not l.strip().startswith("0:0")
            and "Audio original" not in l
        ]
        text = "\n".join(lines[:40]) if lines else ""
        return {"text": text, "image_url": image_url}

    except Exception as e:
        logger.warning("[fetch_facebook] Error scraping post %s: %s", url, e)
        return {"text": "", "image_url": ""}


async def _scrape_search_feed(page) -> tuple[str, str]:
    """
    Extrae texto del feed de resultados de búsqueda de FB.
    Retorna (texto_combinado, image_url).
    Los resultados de búsqueda de FB no exponen links /posts/pfbid en el DOM —
    el contenido está inline en el feed.
    """
    # Expandir "Ver más" visibles
    try:
        expandables = await page.query_selector_all("[role='button'], button, a")
        clicked = 0
        for el in expandables:
            try:
                text = (await el.inner_text()).strip()
                if text in ("Ver más", "See more"):
                    await el.click()
                    await page.wait_for_timeout(400)
                    clicked += 1
            except Exception:
                pass
        if clicked:
            logger.info("[fetch_facebook] Expandidos %d 'Ver más'", clicked)
            await page.wait_for_timeout(1_000)
    except Exception:
        pass

    await page.wait_for_timeout(1_000)

    if os.getenv("FB_DEBUG"):
        debug_dir = Path(__file__).parent.parent.parent / "data" / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(debug_dir / "fb_search_after_expand.png"), full_page=False)
        logger.info("[fetch_facebook] DEBUG screenshot guardado")

    # Texto del feed
    raw = ""
    try:
        feed = await page.query_selector("[role='feed']")
        if feed:
            raw = await feed.inner_text()
    except Exception:
        pass

    if not raw.strip():
        return "", ""

    lines = [
        l.strip() for l in raw.split("\n")
        if len(l.strip()) > 5
        and l.strip() not in _UI_NOISE
        and not l.strip().startswith("0:0")
        and "Audio original" not in l
    ]
    if not lines:
        return "", ""

    logger.info("[fetch_facebook] Search feed: %d líneas extraídas", len(lines))

    # Primera imagen de contenido del feed (no avatares)
    image_url = ""
    try:
        imgs = await page.query_selector_all("[role='feed'] img[src*='fbcdn.net']")
        for img in imgs:
            src = await img.get_attribute("src") or ""
            if src and "scontent" in src:
                image_url = src
                logger.info("[fetch_facebook] imagen del feed de búsqueda capturada")
                break
    except Exception:
        pass

    return "\n".join(lines[:150]), image_url


async def _search_and_scrape(page, query: str, page_id: str = "") -> list[dict]:
    """
    Navega a la URL de búsqueda directa de la página.
    Fallback: scraping del feed con seeds si la búsqueda no rinde resultados.
    Retorna list[{text, image_url}].
    """
    import urllib.parse

    numeric_id = _PAGE_NUMERIC_IDS.get(page_id)
    if numeric_id:
        try:
            search_url = (
                f"https://www.facebook.com/profile/{numeric_id}/search"
                f"?q={urllib.parse.quote(query)}"
            )
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(5_000)
            logger.info("[fetch_facebook] Búsqueda directa: '%s' → %s", query, search_url)

            if os.getenv("FB_DEBUG"):
                debug_dir = Path(__file__).parent.parent.parent / "data" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                await page.screenshot(
                    path=str(debug_dir / f"fb_search_{page_id}_{query[:20].replace(' ', '_')}.png"),
                    full_page=False,
                )

            text, image_url = await _scrape_search_feed(page)
            if text:
                return [{"text": text, "image_url": image_url}]
            logger.info("[fetch_facebook] Búsqueda sin resultados, volviendo al feed")
        except Exception as e:
            logger.warning("[fetch_facebook] Error en búsqueda directa: %s", e)
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
}

_POST_URL_PATTERNS = ("/posts/", "/photo.php", "/reel/", "/videos/")
