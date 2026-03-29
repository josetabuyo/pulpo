"""
Node: fetch_facebook

Scrapea los posts recientes de una página pública de Facebook usando Playwright.
Requiere una cuenta FB con acceso (FB_EMAIL + FB_PASSWORD en .env).
Guarda cookies en data/sessions/fb-{page_id}/ para no hacer login en cada llamada.
Cachea el resultado en memoria por CACHE_TTL segundos.

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

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="es-AR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )

        # Cargar cookies guardadas si existen
        if cookies_path.exists():
            try:
                saved = json.loads(cookies_path.read_text())
                await ctx.add_cookies(saved)
                logger.info("[fetch_facebook] Cookies cargadas desde disco")
            except Exception as e:
                logger.warning("[fetch_facebook] Error cargando cookies: %s", e)

        page = await ctx.new_page()

        # Ir a la página objetivo
        await page.goto(
            f"https://www.facebook.com/{page_id}",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(2_500)

        # Si nos redirigió al login, autenticamos
        if "login" in page.url or "checkpoint" in page.url:
            logger.info("[fetch_facebook] Login requerido, autenticando...")
            ok = await _do_login(page, email, password)
            if not ok:
                await browser.close()
                return ""

            # Guardar cookies para la próxima vez
            fresh_cookies = await ctx.cookies()
            cookies_path.write_text(json.dumps(fresh_cookies, ensure_ascii=False))
            logger.info("[fetch_facebook] Cookies guardadas en %s", cookies_path)

            # Volver a la página
            await page.goto(
                f"https://www.facebook.com/{page_id}",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await page.wait_for_timeout(3_000)

        # Scrapear posts (con o sin búsqueda)
        if query:
            posts = await _search_and_scrape(page, query)
        else:
            posts = await _scrape_posts(page)

        await browser.close()

    if not posts:
        logger.warning("[fetch_facebook] No se encontraron posts para '%s'", page_id)
        return ""

    result = "\n\n".join(posts)
    logger.info("[fetch_facebook] %d posts extraídos para '%s'", len(posts), page_id)
    return result


async def _do_login(page, email: str, password: str) -> bool:
    try:
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(1_000)
        await page.fill("#email", email)
        await page.fill("#pass", password)
        await page.click("[name='login']")
        await page.wait_for_timeout(5_000)

        if "login" not in page.url and "checkpoint" not in page.url:
            logger.info("[fetch_facebook] Login exitoso")
            return True

        logger.error("[fetch_facebook] Login falló. URL actual: %s", page.url)
        return False
    except Exception as e:
        logger.error("[fetch_facebook] Excepción en login: %s", e)
        return False


async def _search_and_scrape(page, query: str) -> list[str]:
    """Usa el botón Buscar de la página si está disponible, sino scrapea todo."""
    try:
        # El botón "Buscar" aparece en el perfil cuando hay login
        btn = await page.query_selector("div[aria-label='Buscar']")
        if not btn:
            btn = await page.query_selector("button[aria-label='Buscar']")

        if btn:
            await btn.click()
            await page.wait_for_timeout(800)
            await page.keyboard.type(query)
            await page.wait_for_timeout(2_500)
            logger.info("[fetch_facebook] Búsqueda: '%s'", query)
        else:
            logger.info("[fetch_facebook] Sin botón Buscar, usando todos los posts")
    except Exception as e:
        logger.warning("[fetch_facebook] Error usando buscador: %s", e)

    return await _scrape_posts(page)


_UI_NOISE = {
    "Me gusta", "Comentar", "Compartir", "Ver más", "Luganense",
    "Todo", "Publicaciones", "Información", "Fotos", "Seguidores", "Menciones",
    "Reels", "Grupos", "Marketplace",
}


async def _scrape_posts(page) -> list[str]:
    """Extrae texto de los posts visibles en la página."""
    # Scroll para que el feed cargue
    await page.evaluate("window.scrollBy(0, 600)")
    await page.wait_for_timeout(2_000)
    await page.evaluate("window.scrollBy(0, 600)")
    await page.wait_for_timeout(1_500)

    posts: list[str] = []
    try:
        # Selector principal: bloques de mensaje de post
        els = await page.query_selector_all("div[data-ad-preview='message']")

        # Fallback: artículos genéricos
        if not els:
            els = await page.query_selector_all("[role='article']")

        for el in els[:_MAX_POSTS]:
            raw = await el.inner_text()
            lines = [
                l.strip() for l in raw.split("\n")
                if len(l.strip()) > 25 and l.strip() not in _UI_NOISE
            ]
            if lines:
                posts.append("\n".join(lines[:15]))

    except Exception as e:
        logger.error("[fetch_facebook] Error scraping posts: %s", e)

    return posts
