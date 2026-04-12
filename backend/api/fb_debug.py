"""
Herramienta de debug interactivo para scraping de Facebook.

Endpoints:
  POST /api/debug/fb/start   — abre browser y navega a búsqueda (sesión persistente)
  POST /api/debug/fb/eval    — inyecta JS en la sesión activa
  DELETE /api/debug/fb/stop  — cierra la sesión

  GET  /api/debug/fb/search  — búsqueda one-shot (mismo código que producción) + info DOM

Todos requieren x-password: <ADMIN_PASSWORD>
"""
import asyncio
import json
import logging
import os
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Body, HTTPException
from api.deps import require_admin

router = APIRouter()
logger = logging.getLogger(__name__)

_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ── Sesión persistente ────────────────────────────────────────────────────────
# Una sola sesión a la vez (debug es single-user)
_session: dict[str, Any] = {}   # keys: browser, page, pw_ctx (playwright context manager)


@router.post("/debug/fb/start", dependencies=[Depends(require_admin)])
async def fb_start(
    page_id:    str = Body("luganense"),
    numeric_id: str = Body("100070998865103"),
    query:      str = Body(""),
    headless:   bool = Body(False),
):
    """
    Abre un browser y navega a la búsqueda de FB (o al perfil si query vacío).
    El browser queda abierto hasta llamar DELETE /api/debug/fb/stop.
    """
    global _session

    if _session.get("browser"):
        return {"error": "Ya hay una sesión activa. Llamá DELETE /api/debug/fb/stop primero."}

    cookies_path = _SESSIONS_DIR / f"fb-{page_id}" / "cookies.json"
    if not cookies_path.exists():
        return {"error": f"Sin cookies para '{page_id}'. Hacer login primero."}

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    ctx = await browser.new_context(
        locale="es-AR",
        user_agent=_UA,
        viewport={"width": 1400, "height": 900},
    )
    await ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    saved = json.loads(cookies_path.read_text())
    await ctx.add_cookies(saved)
    page = await ctx.new_page()

    if query:
        url = (
            f"https://www.facebook.com/profile/{numeric_id}/search"
            f"?q={urllib.parse.quote(query)}"
        )
    else:
        url = f"https://www.facebook.com/{page_id}/posts"

    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(4_000)

    _session = {"pw": pw, "browser": browser, "ctx": ctx, "page": page, "url": url}
    logger.info("[fb_debug] Sesión iniciada: %s", url)

    return {"status": "ok", "url": url, "headless": headless}


@router.post("/debug/fb/eval", dependencies=[Depends(require_admin)])
async def fb_eval(js: str = Body(..., embed=True)):
    """
    Evalúa JS en la sesión activa y retorna el resultado.
    Ejemplo body: {"js": "document.title"}
    """
    page = _session.get("page")
    if not page:
        raise HTTPException(400, "No hay sesión activa. Llamá POST /api/debug/fb/start primero.")
    try:
        result = await page.evaluate(js)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@router.post("/debug/fb/share_url_hunt", dependencies=[Depends(require_admin)])
async def fb_share_url_hunt(
    post_index: int = Body(0, description="Índice del post (0=primero)"),
):
    """
    Hace click en el botón Compartir del post indicado, captura TODAS las respuestas
    de red durante el proceso, busca cualquier URL share/p/ en ellas.
    También intenta click en Copiar enlace y lee el clipboard.
    """
    page = _session.get("page")
    ctx = _session.get("ctx")
    if not page:
        raise HTTPException(400, "No hay sesión activa.")

    share_urls_found: list[str] = []
    responses_with_share: list[str] = []

    async def on_response(response):
        try:
            if "share" in response.url or "graphql" in response.url or "ajax" in response.url:
                try:
                    body = await response.text()
                    if "share/p/" in body or "share\\/p\\/" in body:
                        # Extraer la URL
                        import re
                        matches = re.findall(r'https://www\.facebook\.com/share/p/[\w]+/?', body)
                        matches += re.findall(r'https:\\/\\/www\\.facebook\\.com\\/share\\/p\\/[\\w]+\\/?', body)
                        responses_with_share.extend(matches)
                        if not matches:
                            responses_with_share.append(f"[match en {response.url[:80]}]")
                except Exception:
                    pass
        except Exception:
            pass

    page.on("response", on_response)

    try:
        # Grant clipboard permission (por si acaso)
        if ctx:
            try:
                await ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://www.facebook.com")
            except Exception:
                pass

        # Click en el botón Compartir del post indicado
        feed = await page.query_selector("[role='feed']")
        if not feed:
            return {"error": "no feed"}
        posts = await feed.query_selector_all(":scope > div")
        if post_index >= len(posts):
            return {"error": f"solo hay {len(posts)} posts"}

        post = posts[post_index]
        share_btn = await post.query_selector("[aria-label='Envía esto a tus amigos o publícalo en tu perfil.']")
        if not share_btn:
            return {"error": "botón compartir no encontrado en post"}

        await share_btn.click(force=True)
        await page.wait_for_timeout(2500)

        # Click en Copiar enlace dentro del diálogo Compartir
        url_clicked = await page.evaluate("""() => {
            const d = Array.from(document.querySelectorAll('[role=dialog]'))
                .find(d => d.innerText.includes('Compartir ahora'));
            if (!d) return 'no Compartir dialog';
            const btn = Array.from(d.querySelectorAll('div,span'))
                .find(el => el.innerText && el.innerText.trim() === 'Copiar enlace');
            if (!btn) return 'no Copiar enlace btn';
            btn.click();
            return 'clicked Copiar enlace';
        }""")

        await page.wait_for_timeout(2000)

        # Leer clipboard
        clipboard = ""
        try:
            clipboard = await page.evaluate("navigator.clipboard.readText()")
            if "facebook.com" in clipboard:
                share_urls_found.append(clipboard)
        except Exception as e:
            clipboard = f"error: {e}"

        return {
            "post_index": post_index,
            "click_result": url_clicked,
            "clipboard": clipboard,
            "responses_with_share": responses_with_share,
            "share_urls_found": share_urls_found,
        }
    finally:
        page.remove_listener("response", on_response)


@router.post("/debug/fb/watch_requests", dependencies=[Depends(require_admin)])
async def fb_watch_requests(
    duration_ms: int = Body(3000),
    filter_str: str = Body("share"),
):
    """
    Escucha requests de red durante duration_ms ms y retorna los que contengan filter_str.
    Útil para capturar la URL generada al hacer click en 'Copiar enlace'.
    """
    page = _session.get("page")
    if not page:
        raise HTTPException(400, "No hay sesión activa.")

    captured = []

    def on_request(request):
        if filter_str in request.url:
            captured.append({"url": request.url, "method": request.method})

    page.on("request", on_request)
    await page.wait_for_timeout(duration_ms)
    page.remove_listener("request", on_request)
    return {"captured": captured}


@router.get("/debug/fb/clipboard", dependencies=[Depends(require_admin)])
async def fb_read_clipboard():
    """Lee el contenido del portapapeles del browser de la sesión activa."""
    page = _session.get("page")
    if not page:
        raise HTTPException(400, "No hay sesión activa.")
    try:
        text = await page.evaluate("navigator.clipboard.readText()")
        return {"clipboard": text}
    except Exception as e:
        return {"error": str(e)}


@router.post("/debug/fb/click", dependencies=[Depends(require_admin)])
async def fb_click(
    selector: str = Body(..., description="CSS selector del elemento a clickear"),
    wait_ms: int = Body(2000, description="ms a esperar después del click"),
    eval_js: str = Body("", description="JS opcional a evaluar después del click"),
):
    """
    Hace click en un elemento por selector CSS, espera wait_ms, y evalúa JS opcional.
    Útil para clickear botones y leer el resultado del DOM resultante.
    """
    page = _session.get("page")
    if not page:
        raise HTTPException(400, "No hay sesión activa.")
    try:
        el = await page.query_selector(selector)
        if not el:
            return {"error": f"Selector no encontrado: {selector}"}
        await el.click(force=True)
        await page.wait_for_timeout(wait_ms)
        result = None
        if eval_js:
            result = await page.evaluate(eval_js)
        return {"clicked": selector, "result": result}
    except Exception as e:
        return {"error": str(e)}


@router.delete("/debug/fb/stop", dependencies=[Depends(require_admin)])
async def fb_stop():
    """Cierra la sesión activa."""
    global _session
    browser = _session.get("browser")
    pw = _session.get("pw")
    if not browser:
        return {"status": "no había sesión activa"}
    try:
        await browser.close()
        await pw.stop()
    except Exception as e:
        logger.warning("[fb_debug] Error cerrando sesión: %s", e)
    _session = {}
    logger.info("[fb_debug] Sesión cerrada")
    return {"status": "cerrada"}


@router.get("/debug/fb/search", dependencies=[Depends(require_admin)])
async def fb_search_debug(
    query:      str  = Query(...),
    page_id:    str  = Query("luganense"),
    numeric_id: str  = Query("100070998865103"),
    headless:   bool = Query(True),
    wait:       int  = Query(0, description="Segundos a esperar con browser abierto al final"),
):
    """
    Búsqueda one-shot con el mismo código que producción.
    Retorna texto extraído, share_urls, y auditoría del DOM.
    Con headless=false y wait>0 podés inspeccionar el browser.
    """
    from nodes import fetch_facebook as fb

    # Forzar headless según parámetro
    original_env = os.environ.get("FB_DEBUG")
    if not headless:
        os.environ["FB_DEBUG"] = "1"
    elif "FB_DEBUG" in os.environ:
        del os.environ["FB_DEBUG"]

    # Invalidar caché para forzar scraping fresco
    fb.invalidate(page_id)

    try:
        posts = await fb.fetch_posts(page_id, query, numeric_id)
    finally:
        # Restaurar env
        if original_env is not None:
            os.environ["FB_DEBUG"] = original_env
        elif not headless and "FB_DEBUG" in os.environ:
            del os.environ["FB_DEBUG"]

    result = {
        "query": query,
        "page_id": page_id,
        "posts_found": len(posts),
        "posts": [
            {
                "text_preview": p.get("text", "")[:200],
                "url": p.get("url", ""),
                "post_urls": p.get("post_urls", []),
                "has_image": bool(p.get("image_url")),
            }
            for p in posts
        ],
    }

    if wait > 0 and not headless:
        logger.info("[fb_debug] Esperando %ds con browser abierto...", wait)
        await asyncio.sleep(wait)

    return result
