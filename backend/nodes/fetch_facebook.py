"""
Node: fetch_facebook

Scrapea los posts recientes de una página pública de Facebook usando Playwright.
Requiere una cuenta FB con acceso (FB_EMAIL + FB_PASSWORD en .env).

Login: la primera vez (o cuando las cookies expiran) abre un browser VISIBLE para
       evitar la detección anti-bot de Facebook. El usuario puede ver el proceso.
       Las cookies se guardan en data/sessions/fb-{page_id}/cookies.json.

Scraping: usa browser headless con las cookies guardadas. Cachea 30 min.

Interfaz futura: cuando haya Graph API key, se reemplaza _load() sin tocar el grafo.
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

# cache en memoria: page_id -> (timestamp, texto)
_cache: dict[str, tuple[float, str]] = {}


async def fetch(page_id: str, query: str = "") -> str:
    """
    Devuelve el texto de los últimos posts de una página de Facebook.
    Cachea 30 min. Si se pasa query, intenta usar el buscador de la página.
    """
    cache_key = f"{page_id}:{query}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        logger.debug("[fetch_facebook] cache hit — %s", cache_key)
        return cached[1]

    content = await _load(page_id, query)
    if content:
        _cache[cache_key] = (time.time(), content)
    return content


def invalidate(page_id: str) -> None:
    """Fuerza re-scraping en el próximo fetch."""
    keys = [k for k in _cache if k.startswith(f"{page_id}:")]
    for k in keys:
        del _cache[k]
    logger.info("[fetch_facebook] cache invalidada para '%s'", page_id)


# ─────────────────────────────────────────────────────────────
# Implementación interna (reemplazar por Graph API en el futuro)
# ─────────────────────────────────────────────────────────────

async def _load(page_id: str, query: str) -> str:
    from playwright.async_api import async_playwright

    email = os.getenv("FB_EMAIL", "").strip()
    password = os.getenv("FB_PASSWORD", "").strip()
    if not email or not password:
        logger.error("[fetch_facebook] FB_EMAIL / FB_PASSWORD no configurados")
        return ""

    cookies_path = _SESSIONS_DIR / f"fb-{page_id}" / "cookies.json"
    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    # Sin cookies → login con browser VISIBLE (evita detección anti-bot de FB).
    # Solo ocurre la primera vez o cuando la sesión expira.
    if not cookies_path.exists():
        logger.info("[fetch_facebook] Sin cookies → login con browser visible...")
        ok = await _do_login_visible(email, password, cookies_path)
        if not ok:
            return ""

    # Scraping headless con cookies guardadas
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

        # Si la sesión expiró → borrar cookies para forzar re-login la próxima vez
        if "login" in page.url or "checkpoint" in page.url:
            logger.warning(
                "[fetch_facebook] Sesión expirada — cookies eliminadas, re-login requerido"
            )
            cookies_path.unlink(missing_ok=True)
            await browser.close()
            return ""

        if query:
            posts = await _search_and_scrape(page, query, page_id)
        else:
            posts = await _scrape_posts(page, page_id)

        await browser.close()

    if not posts:
        logger.warning("[fetch_facebook] No se encontraron posts para '%s'", page_id)
        return ""

    result = "\n\n".join(posts)
    logger.info("[fetch_facebook] %d posts extraídos para '%s'", len(posts), page_id)
    return result


async def _do_login_visible(email: str, password: str, cookies_path: Path) -> bool:
    """
    Abre un browser VISIBLE para hacer login en Facebook.
    Evita la detección anti-bot que bloquea formularios en headless.
    Guarda las cookies en cookies_path.
    """
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            ctx = await browser.new_context(locale="es-AR", user_agent=_UA)
            page = await ctx.new_page()

            await page.goto(
                "https://www.facebook.com/login",
                wait_until="domcontentloaded",
                timeout=20_000,
            )
            await page.wait_for_timeout(1_500)

            await page.wait_for_selector("input[name='email']", timeout=15_000)
            await page.fill("input[name='email']", email)
            await page.fill("input[name='pass']", password)
            await page.press("input[name='pass']", "Enter")
            await page.wait_for_timeout(6_000)

            url = page.url
            if "login" in url or "checkpoint" in url:
                logger.error("[fetch_facebook] Login falló. URL: %s", url)
                await browser.close()
                return False

            fresh_cookies = await ctx.cookies()
            cookies_path.write_text(json.dumps(fresh_cookies, ensure_ascii=False))
            logger.info("[fetch_facebook] Login exitoso — cookies guardadas en %s", cookies_path)
            await browser.close()
            return True

    except Exception as e:
        logger.error("[fetch_facebook] Excepción en login visible: %s", e)
        return False


async def _find_buscar_button(page):
    """Encuentra el botón 'Buscar' del perfil de la página (no el buscador global)."""
    try:
        buttons = await page.query_selector_all("main button")
        for btn in buttons:
            text = (await btn.inner_text()).strip()
            if text == "Buscar":
                return btn
    except Exception:
        pass
    return None


async def _search_and_scrape(page, query: str, page_id: str = "") -> list[str]:
    """
    Navega a la URL de búsqueda de la página directamente.
    Requiere el ID numérico de FB en _PAGE_NUMERIC_IDS.
    Fallback: scrapea todos los posts del feed.
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
            results = await _scrape_posts(page, page_id)
            if results:
                return results
            logger.info("[fetch_facebook] Búsqueda sin resultados, volviendo al feed")
        except Exception as e:
            logger.warning("[fetch_facebook] Error en búsqueda directa: %s", e)
    else:
        logger.info("[fetch_facebook] Sin ID numérico para '%s', usando feed", page_id)

    # Fallback: feed con seeds
    return await _scrape_posts(page, page_id)


# URLs conocidas de Destacados por page_id (extraídas via browser MCP).
# Se agregan como seeds si no aparecen en el feed headless.
_SEED_URLS: dict[str, list[str]] = {
    "luganense": [
        # Destacados fijados (actualizados 2026-03-29)
        "https://www.facebook.com/luganense/posts/pfbid0UYq8USWM2BtCxJEC6wK9yzf5T226iG8mqnHGWxWR19z6JaAnQkiQLyBUUTGYYCPYl",
        "https://www.facebook.com/luganense/posts/pfbid0y3qNc2B6pqN3d9HHTpNwT8c7JoxKj6AMcTH7kEj7UTkQL59r7h3drAHg5Pg8hSMil",
        # Posts recientes del feed (extraídos vía fotos 2026-03-29)
        "https://www.facebook.com/luganense/posts/pfbid0ztrskdpEdKwrisPNv5eppiqa6j921H5b8mr7aEW1LqEkh2YsDZQHbf5nqFAfKBRgl",  # Heladería Lordie
        "https://www.facebook.com/luganense/posts/pfbid02ybisUk22dqo5e8Pfwdo2wJYUjDtYReNrNBWKnjbhiNiy1HJNYUaX9ii9Rz88HDcxl",  # Perro/mascota
        "https://www.facebook.com/luganense/posts/pfbid02eMA9gfcEz67bbpxu9t51zdWN2nqet8KATynjaqUxc5oUJ5Hc79Uo61kfZLaY5CVDl",  # Post barrio
    ]
}

# IDs numéricos de FB para usar la URL de búsqueda directa
# (/profile/{numeric_id}/search?q=...)
_PAGE_NUMERIC_IDS: dict[str, str] = {
    "luganense": "100070998865103",
}

# Posts de reels que no se pueden scrapearse en headless.
# Texto extraído manualmente vía MCP browser (2026-03-29).
_STATIC_POSTS: dict[str, list[str]] = {
    "luganense": [
        # Reel /reel/2370482426798630 — Pollería Sabor Peruano (inauguración)
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
}

_POST_URL_PATTERNS = ("/posts/", "/photo.php", "/reel/", "/videos/")


async def _post_urls_from_photos(ctx, page_id: str, max_photos: int = 6) -> list[str]:
    """
    Estrategia alternativa para encontrar posts recientes:
    1. Va a /luganense/photos (carga bien en headless)
    2. Por cada foto, navega a ella y extrae el link "Ver publicación"
    3. Retorna los pfbid de los posts más recientes

    Las fotos del perfil están en orden cronológico inverso → las primeras son las más recientes.
    """
    photo_page = await ctx.new_page()
    post_urls: list[str] = []
    seen: set[str] = set()

    try:
        await photo_page.goto(
            f"https://www.facebook.com/{page_id}/photos",
            wait_until="domcontentloaded",
            timeout=20_000,
        )
        await photo_page.wait_for_timeout(2_500)

        # Recolectar URLs de fotos individuales (photo.php?fbid=... o /photo/?fbid=...)
        links = await photo_page.query_selector_all("a[href*='fbid=']")
        photo_urls: list[str] = []
        photo_seen: set[str] = set()
        for link in links:
            href = await link.get_attribute("href") or ""
            if "fbid=" not in href:
                continue
            # Saltar la foto de portada (fbid muy bajo = foto antigua)
            base = href.split("?")[0] + "?" + href.split("?")[1].split("&")[0] if "?" in href else href
            if base not in photo_seen:
                photo_seen.add(base)
                photo_urls.append(href)
            if len(photo_urls) >= max_photos:
                break

        logger.info("[fetch_facebook] %d fotos recientes encontradas", len(photo_urls))

        # Para cada foto, extraer el pfbid del post al que pertenece
        seen_posts: set[str] = set()
        for photo_url in photo_urls:
            try:
                fp = await ctx.new_page()
                full_url = (
                    f"https://www.facebook.com{photo_url}"
                    if photo_url.startswith("/")
                    else photo_url
                )
                await fp.goto(full_url, wait_until="domcontentloaded", timeout=15_000)
                await fp.wait_for_timeout(1_500)

                # Buscar el link "Ver publicación"
                ver_pub = await fp.query_selector("a[href*='/posts/pfbid']")
                if ver_pub:
                    post_href = (await ver_pub.get_attribute("href") or "").split("?")[0]
                    if post_href and post_href not in seen_posts:
                        seen_posts.add(post_href)
                        post_urls.append(post_href)
                        logger.debug("[fetch_facebook] Foto → post: %s", post_href[-30:])

                await fp.close()
            except Exception as e:
                logger.debug("[fetch_facebook] Error en foto: %s", e)
                try:
                    await fp.close()
                except Exception:
                    pass

    except Exception as e:
        logger.warning("[fetch_facebook] Error en _post_urls_from_photos: %s", e)
    finally:
        await photo_page.close()

    logger.info("[fetch_facebook] %d post URLs via fotos", len(post_urls))
    return post_urls


async def _collect_post_urls(page, page_id: str) -> list[str]:
    """
    Recolecta URLs de posts individuales.
    Prioridad:
    1. Seeds hardcodeados (pfbid que funcionan en headless)
    2. Links del feed headless (lo que cargue)
    """
    urls: list[str] = []
    seen: set[str] = set()

    # Seeds conocidos (Destacados + posts recientes)
    for seed in _SEED_URLS.get(page_id, []):
        base = seed.split("?")[0]
        if base not in seen:
            seen.add(base)
            urls.append(base)

    # Links del feed headless — por si algo más aparece
    for _ in range(4):
        await page.evaluate("window.scrollBy(0, 800)")
        await page.wait_for_timeout(1_500)

    try:
        links = await page.query_selector_all("a[href]")
        for link in links:
            href = await link.get_attribute("href") or ""
            if not any(p in href for p in _POST_URL_PATTERNS):
                continue
            # Normalizar URL
            if href.startswith("/"):
                href = f"https://www.facebook.com{href}"
            # Limpiar parámetros de tracking
            base = href.split("?")[0]
            if base not in seen:
                seen.add(base)
                urls.append(base)
    except Exception as e:
        logger.error("[fetch_facebook] Error recolectando URLs: %s", e)

    logger.info("[fetch_facebook] %d URLs de posts encontradas", len(urls))
    return urls[:_MAX_POSTS]


async def _scrape_post_page(ctx, url: str) -> str:
    """
    Navega a un post individual y extrae el texto completo (sin truncar).
    Los posts individuales no tienen "Ver más" — carga el texto completo.
    """
    try:
        post_page = await ctx.new_page()
        await post_page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        await post_page.wait_for_timeout(2_000)

        # Expandir texto truncado: clicar el botón "Ver más" si existe
        try:
            ver_mas = await post_page.query_selector("button:has-text('Ver más'), [role='button']:has-text('Ver más')")
            if ver_mas:
                await ver_mas.click()
                await post_page.wait_for_timeout(800)
        except Exception:
            pass

        # Primero intentar el article principal del post
        raw = ""
        articles = await post_page.query_selector_all("[role='article']")
        if articles:
            # El primer article suele ser el post principal
            raw = await articles[0].inner_text()

        # Si el article no dio contenido útil, usar el body completo
        if len(raw.strip()) < 30:
            raw = await post_page.inner_text("body")

        await post_page.close()

        lines = [
            l.strip() for l in raw.split("\n")
            if len(l.strip()) > 10
            and l.strip() not in _UI_NOISE
            and not l.strip().startswith("0:0")   # timestamps de video
            and "Audio original" not in l
        ]
        return "\n".join(lines[:40]) if lines else ""

    except Exception as e:
        logger.warning("[fetch_facebook] Error scraping post %s: %s", url, e)
        return ""


async def _scrape_posts(page, page_id: str = "") -> list[str]:
    """
    Recolecta URLs de posts visibles en el perfil, navega a cada una
    individualmente y extrae el texto completo (sin "Ver más").
    Incluye también posts estáticos (reels no scrapeables en headless).
    """
    # Posts estáticos hardcodeados (reels, posts de video, etc.)
    posts: list[str] = list(_STATIC_POSTS.get(page_id, []))

    urls = await _collect_post_urls(page, page_id)
    if not urls:
        logger.warning("[fetch_facebook] No se encontraron URLs de posts")
        return posts

    ctx = page.context

    for url in urls:
        text = await _scrape_post_page(ctx, url)
        if text:
            posts.append(text)

    return posts
