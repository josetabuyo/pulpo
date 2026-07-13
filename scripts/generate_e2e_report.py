"""
Genera un reporte HTML estático de los tests e2e de un flow puntual de un bot:
el diagrama REAL del editor de flows (capturado headless contra
`/embed/flow/<bot_id>`, mismo componente @xyflow/react, mismos colores,
mismas flechas — ver `tests/e2e/luganense/capture_diagram.py` y
`frontend/src/pages/EmbedFlowPage.jsx`, cero reconstrucción/duplicado) y,
para cada conversación e2e, una vista partida — la conversación como chat a
la izquierda, lo que se validó a la derecha.

Las conversaciones y sus validaciones NO viven acá — vienen de
`tests/e2e/luganense/scenarios_orquestador_vendedor_mejorado.py`, la misma
fuente que usa `test_orquestador_vendedor_mejorado_sim.py` (pytest). Un solo
lugar, sin duplicar lógica entre el test y el reporte — si se agrega/cambia
un escenario, este reporte lo refleja solo.

Un bot puede tener N flows activos (con distintos triggers) y M inactivos —
este script genera UN reporte por flow (BOT_SLUG/FLOW_SLUG/FLOW_NAME, ver el
módulo de escenarios), no un reporte por bot. El diagrama se resuelve por
FLOW_NAME contra el flow ACTIVO de ese nombre (GET /api/flows/bots/{bot_id}),
no por un flow_id fijo — así el reporte no depende de un UUID que cambia
entre entornos. `--flow-id` fuerza un flow puntual si hace falta.

Uso: correr con el frontend (Vite, :5173) y el backend (:8000) levantados.

    uv run python scripts/generate_e2e_report.py [--skip-telegram]

El diagrama se captura solo, sin pasos manuales (sin loguearse, sin abrir el
editor a mano, sin recortar un screenshot) — `--diagram-image` queda como
escape hatch para forzar un PNG puntual si el frontend no está disponible.

Escribe reports/test-report-e2e-<bot_slug>-<flow_slug>-<fecha>.html
(reports/ se commitea a propósito, ver conftest.py). Este reporte es el que
se le pasa a Luganense para su sección de reportes de test — avisarle recién
después de revisarlo.

No reemplaza reports/test-report.json (ese es el resumen unitario/integration
que genera conftest.py en cada corrida de pytest) — este es específico de
las conversaciones e2e, pensado para lectura humana, no para CI.
"""
import argparse
import asyncio
import base64
import html
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e.luganense.capture_diagram import DiagramCaptureError, capture_flow_diagram
from tests.e2e.luganense.scenarios_orquestador_vendedor_mejorado import (
    BOT_ID, BOT_SLUG, FLOW_NAME, FLOW_SLUG, SCENARIOS, ScenarioResult,
)


def embed_diagram_png_bytes(data: bytes) -> str:
    """
    Ajusta el diagrama al ancho del reporte (fit horizontal, sin recorte) y
    lo despliega entero — sin scroll interno, la página scrollea normal si
    hace falta. Clic (o doble clic) abre un lightbox in-page a resolución
    nativa con scroll propio — nada de `window.open`/pestaña nueva, que en
    un HTML embebido en un iframe con sandbox/CSP estricto (ej. un Artifact)
    puede quedar bloqueado en silencio sin dar ningún feedback.
    """
    b64 = base64.b64encode(data).decode("ascii")
    src = f"data:image/png;base64,{b64}"
    return (
        f'<img id="diagram-img" src="{src}" alt="Diagrama del flow (clic para ampliar)" '
        f'title="Clic para ampliar" '
        f'onclick="openDiagramLightbox()" ondblclick="openDiagramLightbox()" '
        f'style="width:100%;height:auto;border-radius:8px;display:block;cursor:zoom-in;">'
    )


async def resolve_active_flow_id(bot_id: str, flow_name: str, backend_url: str) -> str:
    """GET /api/flows/bots/{bot_id} y devuelve el id del flow ACTIVO cuyo nombre
    matchea `flow_name` — así el reporte no depende de un UUID fijo entre entornos."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{backend_url}/api/flows/bots/{bot_id}")
        resp.raise_for_status()
        flows = resp.json()
    match = next((f for f in flows if f.get("name") == flow_name and f.get("active")), None)
    if not match:
        raise SystemExit(
            f"No se encontró un flow ACTIVO llamado {flow_name!r} para bot={bot_id!r} "
            f"en {backend_url} (flows disponibles: {[f.get('name') for f in flows]!r})"
        )
    return match["id"]


def esc(s):
    return html.escape(s or "")


def render_scenario(sc, result: ScenarioResult, idx):
    # El status del escenario (OK/REVISAR) solo depende de los "assert" —
    # los "log" son informativos (decisiones semánticas de un LLM, no
    # deterministas) y nunca lo cambian, ver docstring del módulo de escenarios.
    asserts = [c for c in result.checks if c.kind == "assert"]
    all_ok = all(c.passed for c in asserts)
    status = "OK" if all_ok else "REVISAR"
    status_color = "#22c55e" if all_ok else "#f59e0b"
    bubbles = "".join(
        f'<div class="bubble {role}"><span class="role">{"Vecino" if role=="user" else "Luganense"}</span>{esc(text)}</div>'
        for role, text in result.turns
    )

    def _render_check(c):
        if c.kind == "log":
            return (
                '<li class="info"><span class="mark">·</span>'
                f'<div><div>{esc(c.label)}</div>'
                + (f'<div class="detail">{esc(c.detail)}</div>' if c.detail else "")
                + "</div></li>"
            )
        return (
            f'<li class="{"pass" if c.passed else "fail"}">'
            f'<span class="mark">{"✓" if c.passed else "✗"}</span>'
            f'<div><div>{esc(c.label)}</div>'
            + (f'<div class="detail">{esc(c.detail)}</div>' if c.detail else "")
            + "</div></li>"
        )

    checks_html = "".join(_render_check(c) for c in result.checks)
    badge = '<span class="tg-badge">TELEGRAM REAL</span>' if sc.real_telegram else ""
    return f"""
    <section class="scenario" id="{sc.id}">
      <div class="scenario-head">
        <h3>{idx}. {esc(sc.title)} {badge}</h3>
        <span class="status" style="color:{status_color};border-color:{status_color}">{status}</span>
      </div>
      <p class="scenario-desc">{esc(sc.desc)}</p>
      <div class="split">
        <div class="conversation">{bubbles}</div>
        <div class="validation"><ul>{checks_html}</ul></div>
      </div>
    </section>
    """


def render_html(diagram_html, pairs, meta):
    total = len(pairs)
    ok = sum(1 for _, r in pairs if all(c.passed for c in r.checks if c.kind == "assert"))
    scenario_html = "".join(render_scenario(sc, r, i + 1) for i, (sc, r) in enumerate(pairs))
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Reporte e2e — {meta['bot_display']} — {meta['flow_name']} — {meta['date']}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #0b1220; color: #e2e8f0;
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5;
  }}
  header {{ padding: 32px 40px 20px; border-bottom: 1px solid #1e293b; }}
  header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  header .meta {{ color: #94a3b8; font-size: 13px; }}
  .summary {{
    display: inline-block; margin-top: 14px; padding: 6px 14px; border-radius: 20px;
    background: {'#052e16' if ok==total else '#451a03'}; color: {'#4ade80' if ok==total else '#fbbf24'};
    font-weight: 600; font-size: 13px; border: 1px solid {'#166534' if ok==total else '#92400e'};
  }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 30px 40px 60px; }}
  h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; margin: 40px 0 14px; }}
  .diagram-wrap {{ border: 1px solid #1e293b; border-radius: 14px; padding: 12px; background: #0f172a; }}
  .scenario {{ margin-bottom: 26px; border: 1px solid #1e293b; border-radius: 12px; padding: 18px 20px; background: #0f172a; }}
  .scenario-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
  .scenario-head h3 {{ margin: 0; font-size: 15px; display: flex; align-items: center; gap: 8px; }}
  .status {{ font-size: 11px; font-weight: 700; letter-spacing: 0.05em; border: 1px solid; border-radius: 6px; padding: 2px 10px; white-space: nowrap; }}
  .scenario-desc {{ color: #94a3b8; font-size: 13px; margin: 8px 0 16px; }}
  .tg-badge {{ font-size: 10px; font-weight: 700; letter-spacing: 0.05em; color: #60a5fa; background: rgba(96,165,250,.12); border: 1px solid #1d4ed8; border-radius: 4px; padding: 1px 6px; }}
  .split {{ display: grid; grid-template-columns: 1.2fr 1fr; gap: 18px; }}
  @media (max-width: 760px) {{ .split {{ grid-template-columns: 1fr; }} }}
  .conversation {{ display: flex; flex-direction: column; gap: 8px; background: #0b1220; border: 1px solid #1e293b; border-radius: 10px; padding: 14px; }}
  .bubble {{ max-width: 88%; padding: 8px 12px; border-radius: 10px; font-size: 13px; white-space: pre-wrap; }}
  .bubble .role {{ display: block; font-size: 9px; text-transform: uppercase; letter-spacing: .05em; opacity: .55; margin-bottom: 3px; }}
  .bubble.user {{ align-self: flex-end; background: #1e3a5f; border: 1px solid #2563eb; }}
  .bubble.bot {{ align-self: flex-start; background: #1e293b; border: 1px solid #334155; }}
  .validation ul {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }}
  .validation li {{ display: flex; gap: 8px; font-size: 13px; align-items: flex-start; }}
  .validation .mark {{ font-weight: 700; width: 16px; flex-shrink: 0; }}
  .validation li.pass .mark {{ color: #4ade80; }}
  .validation li.fail .mark {{ color: #f87171; }}
  .validation li.info {{ opacity: .7; }}
  .validation li.info .mark {{ color: #64748b; }}
  .validation .detail {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
  footer {{ text-align: center; color: #475569; font-size: 12px; padding: 30px; }}
  #diagram-lightbox {{
    display: none; position: fixed; inset: 0; z-index: 100; background: rgba(2,6,15,0.92);
    overflow: auto; padding: 40px; text-align: center; cursor: zoom-out;
  }}
  #diagram-lightbox img {{ max-width: none; border-radius: 8px; }}
  #diagram-lightbox .hint {{
    position: fixed; top: 14px; left: 50%; transform: translateX(-50%);
    color: #94a3b8; font-size: 12px; background: #0f172a; border: 1px solid #1e293b;
    border-radius: 20px; padding: 4px 14px;
  }}
</style>
</head>
<body>
<header>
  <h1>Reporte de tests e2e — bot {meta['bot_display']} — flow &quot;{meta['flow_name']}&quot;</h1>
  <div class="meta">Flow &quot;{meta['flow_name']}&quot; · generado {meta['date']} · motor: simulador in-band (sin Telegram, salvo el smoke de conectividad) · conversaciones completas de punta a punta, ver tests/e2e/{meta['bot_slug']}/scenarios_{meta['flow_slug']}.py</div>
  <div class="summary">{ok}/{total} conversaciones OK</div>
</header>
<main>
  <h2>Diagrama del flow</h2>
  <div class="diagram-wrap">{diagram_html}</div>

  <h2>Conversaciones e2e</h2>
  {scenario_html}
</main>
<footer>Pulpo — reporte generado automáticamente, {meta['date']}</footer>

<div id="diagram-lightbox" onclick="this.style.display='none'">
  <div class="hint">Clic en cualquier lado para cerrar</div>
  <img id="diagram-lightbox-img" alt="Diagrama del flow ampliado">
</div>
<script>
  function openDiagramLightbox() {{
    document.getElementById('diagram-lightbox-img').src = document.getElementById('diagram-img').src;
    document.getElementById('diagram-lightbox').style.display = 'block';
  }}
</script>
</body>
</html>"""


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagram-image", type=Path, default=None,
                         help="Escape hatch: PNG puntual del diagrama en vez de capturarlo del frontend real")
    parser.add_argument("--frontend-url", default="http://localhost:5173",
                         help="Base URL del frontend (Vite) para /embed/flow/<bot_id>")
    parser.add_argument("--backend-url", default="http://localhost:8000",
                         help="Base URL del backend, para resolver el flow_id activo por nombre")
    parser.add_argument("--flow-id", default=None,
                         help="Forzar un flow_id puntual en vez de resolverlo por FLOW_NAME (el activo)")
    parser.add_argument("--diagram-scale", type=int, default=3,
                         help="device_scale_factor del screenshot del diagrama (nitidez)")
    parser.add_argument("--skip-telegram", action="store_true", help="No correr el smoke de conectividad real de Telegram")
    args = parser.parse_args()

    if args.diagram_image:
        if not args.diagram_image.exists():
            raise SystemExit(f"No existe --diagram-image: {args.diagram_image}")
        diagram_html = embed_diagram_png_bytes(args.diagram_image.read_bytes())
    else:
        flow_id = args.flow_id or await resolve_active_flow_id(BOT_ID, FLOW_NAME, args.backend_url)
        print(f"Capturando diagrama del flow {FLOW_NAME!r} (id={flow_id}) contra {args.frontend_url}...")
        try:
            png_bytes = await capture_flow_diagram(
                bot_id=BOT_ID, flow_id=flow_id, base_url=args.frontend_url, scale=args.diagram_scale,
            )
        except DiagramCaptureError as e:
            raise SystemExit(
                f"No se pudo capturar el diagrama ({e}). "
                f"¿Está el frontend levantado en {args.frontend_url}? "
                f"Alternativa: pasar --diagram-image <path.png> a mano."
            )
        diagram_html = embed_diagram_png_bytes(png_bytes)

    pairs = []
    for sc in SCENARIOS:
        if sc.real_telegram and args.skip_telegram:
            continue
        print(f"Corriendo escenario: {sc.id}...")
        try:
            result = await sc.run()
        except Exception as e:
            print(f"  (no se pudo correr {sc.id}: {e})")
            continue
        pairs.append((sc, result))

    date_str = datetime.now().strftime("%Y-%m-%d")
    meta = {
        "date": date_str,
        "bot_slug": BOT_SLUG,
        "flow_slug": FLOW_SLUG,
        "flow_name": FLOW_NAME,
        "bot_display": BOT_SLUG.capitalize(),
    }
    out = render_html(diagram_html, pairs, meta)

    out_path = Path(__file__).resolve().parent.parent / "reports" / f"test-report-e2e-{BOT_SLUG}-{FLOW_SLUG}-{date_str}.html"
    out_path.write_text(out, encoding="utf-8")
    print(f"\nReporte escrito en: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
