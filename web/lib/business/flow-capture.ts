// Captura headless del "gemelo" del flow con el camino resaltado -- puerto a
// TS de tests/e2e/luganense/capture_diagram.py (Playwright, chromium
// headless), pero apuntando a /embed/test-run/{botId}/{runId} en vez de
// /embed/flow/{botId}: esa ruta (frontend/src/pages/EmbedTestRunPage.jsx)
// monta el mismo FlowCanvas real en modo embed con `highlightNodeIds`/
// `highlightEdgeIds` (ver utils/executionTrace.js), reusando el mecanismo
// de resaltado del editor -- cero dibujo propio.
//
// Se llama desde test-runner.ts al final de CADA corrida (sin importar si
// la disparó la UI o el CLI, ver web/cli/main.ts "test-cases run"/"test-runs
// run") para que la imagen quede en test_runs.diagram_image como parte del
// reporte. A propósito best-effort: si falla (playwright no instalado,
// timeout, el propio server todavía no levantó del todo) NO tira la
// corrida -- loguea y sigue. El resultado del test importa más que su
// foto.
export async function captureTestRunDiagram(
  botId: string,
  runId: string,
  opts: { timeoutMs?: number; scale?: number } = {},
): Promise<string | null> {
  const timeoutMs = opts.timeoutMs ?? 20_000;
  const scale = opts.scale ?? 2;
  const port = process.env.WEB_BACKEND_PORT ?? process.env.PORT ?? "9010";
  const baseUrl = process.env.PULPO_CAPTURE_BASE_URL ?? `http://localhost:${port}`;
  const url = `${baseUrl}/embed/test-run/${botId}/${runId}`;

  let playwright: typeof import("playwright");
  try {
    playwright = await import("playwright");
  } catch {
    console.warn("[flow-capture] paquete 'playwright' no disponible -- se omite la imagen del reporte");
    return null;
  }

  const browser = await playwright.chromium.launch().catch((err) => {
    console.warn(`[flow-capture] no se pudo lanzar chromium: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  });
  if (!browser) return null;

  try {
    const viewport = { width: 2400, height: 2000 };
    const page = await browser.newPage({ viewport, deviceScaleFactor: scale });
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });

    try {
      await page.waitForFunction("window.__flowReady === true", { timeout: timeoutMs });
    } catch {
      const flowError = await page.evaluate(() => (window as unknown as { __flowError?: string }).__flowError ?? null);
      throw new Error(flowError ? `EmbedTestRunPage falló: ${flowError}` : `timeout esperando window.__flowReady en ${url}`);
    }

    const bounds = await page.evaluate(() => {
      const selectors = [".react-flow__node", ".react-flow__edge", ".react-flow__edgelabel-renderer *"];
      const els = document.querySelectorAll(selectors.join(","));
      if (!els.length) return null;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const el of els) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        minX = Math.min(minX, r.left);
        minY = Math.min(minY, r.top);
        maxX = Math.max(maxX, r.right);
        maxY = Math.max(maxY, r.bottom);
      }
      return { minX, minY, maxX, maxY };
    });
    if (!bounds) throw new Error(`el flow en ${url} no tiene nodos para recortar`);

    const margin = 60;
    const clip = {
      x: Math.max(0, bounds.minX - margin),
      y: Math.max(0, bounds.minY - margin),
      width: Math.min(bounds.maxX - bounds.minX + margin * 2, viewport.width - Math.max(0, bounds.minX - margin)),
      height: Math.min(bounds.maxY - bounds.minY + margin * 2, viewport.height - Math.max(0, bounds.minY - margin)),
    };
    const png = await page.screenshot({ type: "png", clip });
    return `data:image/png;base64,${png.toString("base64")}`;
  } catch (err) {
    console.warn(`[flow-capture] no se pudo capturar la imagen de la corrida ${runId}: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  } finally {
    await browser.close();
  }
}
