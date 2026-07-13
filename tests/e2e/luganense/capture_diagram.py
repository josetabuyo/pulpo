"""
Captura headless del diagrama REAL del editor de flows — sin screenshot de
ventana completa ni recorte a mano.

`capture_flow_diagram()` navega (Playwright, chromium headless) a
`/embed/flow/<bot_id>[?flow=<flow_id>]` — una ruta del frontend
(`frontend/src/pages/EmbedFlowPage.jsx`) que monta el mismo `FlowCanvas` del
editor real en modo `embed` (sin Controls, sin panel de config, sin
interacción — ver `frontend/src/components/FlowCanvas.jsx`). Cero dibujo
propio acá: se reusa el render real de @xyflow/react tal cual lo ve José en
el editor.

Espera a `window.__flowReady === true` (seteado por `EmbedFlowPage` recién
después de cargar el flow y que React Flow confirme `onInit`, con doble
`requestAnimationFrame` para no capturar un frame a medio encuadrar), y
recorta el screenshot al bounding box real de los nodos (`.react-flow__node`,
con un margen chico) — no a todo el elemento `.react-flow`, que es el
viewport completo y dejaría de fondo el margen vacío que sobra del `fitView`
con `padding` — a `scale`x de densidad de píxeles para que el PNG quede
nítido en el reporte.

Requiere el frontend (Vite, default :5173) y el backend (default :8000, la
API de flows detrás no pide auth) corriendo — ver `./start.sh` en la raíz
del repo.
"""
from playwright.async_api import async_playwright


class DiagramCaptureError(RuntimeError):
    """El frontend no pudo cargar el flow a capturar (ver window.__flowError)."""


async def capture_flow_diagram(
    *,
    bot_id: str = "luganense",
    flow_id: str | None = None,
    base_url: str = "http://localhost:5173",
    scale: int = 3,
    timeout_ms: int = 15000,
) -> bytes:
    url = f"{base_url}/embed/flow/{bot_id}"
    if flow_id:
        url += f"?flow={flow_id}"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=scale)
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_function("window.__flowReady === true", timeout=timeout_ms)
            except Exception:
                flow_error = await page.evaluate("window.__flowError || null")
                if flow_error:
                    raise DiagramCaptureError(f"EmbedFlowPage falló al cargar el flow: {flow_error}")
                raise DiagramCaptureError(
                    f"Timeout esperando window.__flowReady en {url} (¿el frontend está levantado en {base_url}?)"
                )
            bounds = await page.evaluate("""
                () => {
                    const nodes = document.querySelectorAll('.react-flow__node');
                    if (!nodes.length) return null;
                    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                    for (const el of nodes) {
                        const r = el.getBoundingClientRect();
                        minX = Math.min(minX, r.left); minY = Math.min(minY, r.top);
                        maxX = Math.max(maxX, r.right); maxY = Math.max(maxY, r.bottom);
                    }
                    return { minX, minY, maxX, maxY };
                }
            """)
            if not bounds:
                raise DiagramCaptureError(f"El flow en {url} no tiene nodos para recortar")
            margin = 24
            clip = {
                "x": max(0, bounds["minX"] - margin),
                "y": max(0, bounds["minY"] - margin),
                "width": (bounds["maxX"] - bounds["minX"]) + margin * 2,
                "height": (bounds["maxY"] - bounds["minY"]) + margin * 2,
            }
            return await page.screenshot(type="png", clip=clip)
        finally:
            await browser.close()
