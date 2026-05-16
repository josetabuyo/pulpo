"""
test_browser_zoom.py — Verifica que el zoom global (0.5) se aplica correctamente
al contexto del browser y persiste entre navegaciones.

No requiere servidor corriendo: lanza Playwright directamente.
Requiere: pip install playwright pytest-asyncio && playwright install chromium
"""
import pytest
import pytest_asyncio

# El mismo nivel de zoom que usamos en whatsapp.py
EXPECTED_ZOOM = "0.5"

_ZOOM_INIT_SCRIPT = f"""
(() => {{
    const _applyZoom = () => {{
        document.documentElement.style.zoom = '{EXPECTED_ZOOM}';
    }};
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', _applyZoom);
    }} else {{
        _applyZoom();
    }}
}})();
"""


@pytest.fixture(scope="module")
def event_loop_policy():
    # pytest-asyncio necesita esto en algunos entornos
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.mark.asyncio
async def test_zoom_aplicado_en_nueva_pagina():
    """El init_script de zoom debe aplicar zoom=0.5 en cualquier página nueva del contexto."""
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_init_script(_ZOOM_INIT_SCRIPT)

        page = await context.new_page()
        await page.goto("about:blank")

        zoom = await page.evaluate("document.documentElement.style.zoom")
        assert zoom == EXPECTED_ZOOM, f"zoom esperado={EXPECTED_ZOOM!r}, obtenido={zoom!r}"

        await browser.close()


@pytest.mark.asyncio
async def test_zoom_persiste_tras_navegacion():
    """El zoom debe reaplicarse después de navegar a una URL distinta."""
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_init_script(_ZOOM_INIT_SCRIPT)

        page = await context.new_page()
        await page.goto("about:blank")
        await page.goto("about:blank#second")  # segunda navegación

        zoom = await page.evaluate("document.documentElement.style.zoom")
        assert zoom == EXPECTED_ZOOM, f"zoom no persistió tras navegación: {zoom!r}"

        await browser.close()


@pytest.mark.asyncio
async def test_zoom_en_pagina_ya_cargada():
    """Aplicar evaluate() inmediatamente después del launch (como en sesión persistente)."""
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        # Sin init_script, simulamos la aplicación inmediata a página ya cargada
        page = await context.new_page()
        await page.goto("about:blank")
        await page.evaluate(f"document.documentElement.style.zoom = '{EXPECTED_ZOOM}'")

        zoom = await page.evaluate("document.documentElement.style.zoom")
        assert zoom == EXPECTED_ZOOM, f"evaluate inmediato falló: {zoom!r}"

        await browser.close()


@pytest.mark.asyncio
async def test_zoom_coordenadas_elementos_nuevos():
    """
    Cuando el zoom se aplica via init_script (antes del layout de elementos nuevos),
    getBoundingClientRect devuelve coordenadas ZOOMEADAS (ya escaladas).
    Esto es correcto para el scan JS: el filtro window.innerHeight es coherente
    con rect.top en el mismo espacio visual.
    """
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        await context.add_init_script(_ZOOM_INIT_SCRIPT)

        page = await context.new_page()
        await page.goto("about:blank")  # zoom aplicado por init_script aquí
        # Elemento inyectado DESPUÉS del zoom → layout calculado con zoom=0.5
        await page.evaluate(
            "document.body.innerHTML = '<div id=\"box\" style=\"width:200px;height:100px;margin:50px\"></div>'"
        )

        result = await page.evaluate("""() => {
            const zoom = parseFloat(document.documentElement.style.zoom) || 1;
            const r = document.getElementById('box').getBoundingClientRect();
            return { zoom, top: r.top, width: r.width };
        }""")

        # zoom activo = 0.5
        assert result["zoom"] == pytest.approx(0.5, abs=0.01), \
            f"zoom activo esperado 0.5, obtenido {result['zoom']}"

        # Elementos nuevos con zoom activo → getBoundingClientRect devuelve coordenadas zoomeadas
        # margin 50px → top ≈ 25 (50*0.5), width 200px → ≈ 100 (200*0.5)
        assert result["width"] == pytest.approx(100, abs=2), \
            f"width con zoom=0.5 esperado ≈100, obtenido {result['width']}"
        assert result["top"] == pytest.approx(25, abs=2), \
            f"top con zoom=0.5 esperado ≈25, obtenido {result['top']}"

        await browser.close()
