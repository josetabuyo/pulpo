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
    "Chrome/122.0.0.0 Safari/537.36"
)

# cache estructurado: "page_id:query" -> (timestamp, list[dict])
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
        browser = await pw.chromium.launch(headless=headless)
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

            # Esperar hasta 120s a que aparezca c_user (cookie de sesión real en FB)
            logged_in = False
            for _ in range(120):
                cookies = await ctx.cookies()
                if any(c["name"] == "c_user" for c in cookies):
                    logged_in = True
                    break
                await page.wait_for_timeout(1_000)

            if not logged_in:
                logger.error("[fetch_facebook] Timeout esperando login — captcha o 2FA no completado en 120s")
                await browser.close()
                return False

            await page.wait_for_timeout(2_000)

            if "login" in page.url or "checkpoint" in page.url or "index.php" in page.url:
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
        return {"text": text, "image_url": image_url, "url": url}

    except Exception as e:
        logger.warning("[fetch_facebook] Error scraping post %s: %s", url, e)
        return {"text": "", "image_url": ""}


async def _extract_post_urls(page, max_posts: int = 3) -> list[str]:
    """
    Extrae las URLs share/p/ de los posts del feed de búsqueda.

    Estrategia: para cada post, hace click en el botón Compartir y luego en
    Copiar enlace, capturando la URL share/p/ desde la respuesta de red que
    FB genera al hacer click.
    """
    import re as _re

    share_urls: list[str] = []

    try:
        feed = await page.query_selector("[role='feed']")
        if not feed:
            return []
        posts = await feed.query_selector_all(":scope > div")
        logger.info("[fetch_facebook] %d posts en feed para extraer share URLs", len(posts))
    except Exception as e:
        logger.warning("[fetch_facebook] Error buscando posts en feed: %s", e)
        return []

    for i, post in enumerate(posts[:max_posts + 3]):
        if len(share_urls) >= max_posts:
            break
        try:
            share_btn = await post.query_selector(
                "[aria-label='Envía esto a tus amigos o publícalo en tu perfil.']"
            )
            if not share_btn:
                continue

            # Capturar respuestas de red que contengan share/p/
            captured: list[str] = []

            async def on_response(resp, _cap=captured):
                try:
                    if "share" in resp.url or "graphql" in resp.url or "ajax" in resp.url:
                        body = await resp.text()
                        found = _re.findall(r'https://www\.facebook\.com/share/p/[\w]+/?', body)
                        _cap.extend(found)
                except Exception:
                    pass

            page.on("response", on_response)

            try:
                await share_btn.click(force=True)
                await page.wait_for_timeout(2_000)

                # Click en Copiar enlace dentro del diálogo Compartir
                await page.evaluate("""() => {
                    const d = Array.from(document.querySelectorAll('[role=dialog]'))
                        .find(d => d.innerText.includes('Compartir ahora'));
                    if (!d) return;
                    const btn = Array.from(d.querySelectorAll('div,span'))
                        .find(el => el.innerText && el.innerText.trim() === 'Copiar enlace');
                    if (btn) btn.click();
                }""")
                await page.wait_for_timeout(1_500)

            finally:
                page.remove_listener("response", on_response)

            # Cerrar diálogo
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)

            if captured:
                url = captured[0]
                if url not in share_urls:
                    share_urls.append(url)
                    logger.info("[fetch_facebook] share URL extraída: %s", url)
            else:
                logger.info("[fetch_facebook] post %d: no se capturó share URL", i)

        except Exception as e:
            logger.warning("[fetch_facebook] Error extrayendo share URL post %d: %s", i, e)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

    return share_urls


async def _scrape_search_feed(page) -> tuple[str, list[str]]:
    """
    Extrae texto del feed de resultados de búsqueda de FB.
    Retorna (texto_combinado, share_urls_por_post).
    - texto_combinado: feed.inner_text() filtrado (mecanismo original, probado)
    - share_urls_por_post: URLs share/p/ via click Compartir → Copiar enlace
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

    # Texto combinado del feed (mecanismo original — probado y funcionando)
    raw = ""
    try:
        feed = await page.query_selector("[role='feed']")
        if feed:
            raw = await feed.inner_text()
    except Exception:
        pass

    if not raw.strip():
        return "", []

    lines = [
        l.strip() for l in raw.split("\n")
        if len(l.strip()) > 5
        and l.strip() not in _UI_NOISE
        and not l.strip().startswith("0:0")
        and "Audio original" not in l
    ]
    if not lines:
        return "", []

    logger.info("[fetch_facebook] Search feed: %d líneas extraídas", len(lines))

    # Share URLs via click Compartir
    post_urls: list[str] = []
    try:
        post_urls = await _extract_post_urls(page, max_posts=3)
    except Exception as e:
        logger.warning("[fetch_facebook] Error extrayendo share URLs (no crítico): %s", e)

    return "\n".join(lines[:150]), post_urls


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

            text, post_urls = await _scrape_search_feed(page)
            if text:
                # Un dict por share URL; el primero lleva todo el texto
                posts = []
                for i, u in enumerate(post_urls):
                    posts.append({"text": text if i == 0 else "", "image_url": "", "url": u})
                if not posts:
                    posts = [{"text": text, "image_url": "", "url": f"https://www.facebook.com/{page_id}"}]
                logger.info("[fetch_facebook] Búsqueda: %d líneas, %d URLs para '%s'", len(text.splitlines()), len(post_urls), query)
                return posts
            logger.info("[fetch_facebook] Búsqueda sin resultados para query '%s'", query)
            return []
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
}

_POST_URL_PATTERNS = ("/posts/", "/photo.php", "/reel/", "/videos/")
