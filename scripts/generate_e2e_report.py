"""
Genera un reporte HTML estático de los tests e2e del bot Luganense: el
diagrama REAL del editor de flows (captura de pantalla del editor corriendo,
no una reconstrucción — mismo componente @xyflow/react, mismos colores,
mismas flechas) y, para cada conversación e2e, una vista partida — la
conversación como chat a la izquierda, lo que se validó a la derecha.

Las conversaciones y sus validaciones NO viven acá — vienen de
`tests/e2e/luganense/scenarios.py`, la misma fuente que usa
`test_orquestador_vendedor_sim.py` (pytest). Un solo lugar, sin duplicar
lógica entre el test y el reporte — si se agrega/cambia un escenario, este
reporte lo refleja solo.

Uso: correr con el backend local levantado (http://localhost:8000).

    uv run python scripts/generate_e2e_report.py --diagram-image <path.png> [--skip-telegram]

El diagrama NO se genera por código — se captura a mano con playwright-cli
contra el editor real (evita reinventar el render de @xyflow/react):

    playwright-cli open http://localhost:5173/
    # loguear con ADMIN_PASSWORD (.env), ir a Luganense → Flow → abrir el
    # flow activo, click en "Fit View" (⛶) para centrar todo el diagrama
    playwright-cli resize 1800 1400
    playwright-cli screenshot
    # recortar el canvas del editor (sin la barra superior ni el panel
    # derecho vacío) y pasarlo acá con --diagram-image

Escribe reports/test-report-e2e-<fecha>.html (reports/ se commitea a
propósito, ver conftest.py). Este reporte es el que se le pasa a Luganense
para su sección de reportes de test — avisarle recién después de revisarlo.

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e.luganense.scenarios import SCENARIOS, ScenarioResult


def embed_diagram_image(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{data}" alt="Diagrama del flow" style="width:100%;height:auto;border-radius:8px;display:block;">'


def esc(s):
    return html.escape(s or "")


def render_scenario(sc, result: ScenarioResult, idx):
    all_ok = all(c.passed for c in result.checks)
    status = "OK" if all_ok else "REVISAR"
    status_color = "#22c55e" if all_ok else "#f59e0b"
    bubbles = "".join(
        f'<div class="bubble {role}"><span class="role">{"Vecino" if role=="user" else "Luganense"}</span>{esc(text)}</div>'
        for role, text in result.turns
    )
    checks_html = "".join(
        f'<li class="{"pass" if c.passed else "fail"}">'
        f'<span class="mark">{"✓" if c.passed else "✗"}</span>'
        f'<div><div>{esc(c.label)}</div>'
        + (f'<div class="detail">{esc(c.detail)}</div>' if c.detail else "")
        + "</div></li>"
        for c in result.checks
    )
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
    ok = sum(1 for _, r in pairs if all(c.passed for c in r.checks))
    scenario_html = "".join(render_scenario(sc, r, i + 1) for i, (sc, r) in enumerate(pairs))
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Reporte e2e — Luganense — {meta['date']}</title>
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
  .validation .detail {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
  footer {{ text-align: center; color: #475569; font-size: 12px; padding: 30px; }}
</style>
</head>
<body>
<header>
  <h1>Reporte de tests e2e — bot Luganense</h1>
  <div class="meta">Flow "Orquestador Vendedor Mejorado" · generado {meta['date']} · motor: simulador in-band (sin Telegram, salvo el smoke de conectividad) · conversaciones completas de punta a punta, ver tests/e2e/luganense/scenarios.py</div>
  <div class="summary">{ok}/{total} conversaciones OK</div>
</header>
<main>
  <h2>Diagrama del flow</h2>
  <div class="diagram-wrap">{diagram_html}</div>

  <h2>Conversaciones e2e</h2>
  {scenario_html}
</main>
<footer>Pulpo — reporte generado automáticamente, {meta['date']}</footer>
</body>
</html>"""


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagram-image", required=True, type=Path,
                         help="PNG del editor real (ver instrucciones de captura en el docstring del módulo)")
    parser.add_argument("--skip-telegram", action="store_true", help="No correr el smoke de conectividad real de Telegram")
    args = parser.parse_args()

    if not args.diagram_image.exists():
        raise SystemExit(f"No existe --diagram-image: {args.diagram_image}")
    diagram_html = embed_diagram_image(args.diagram_image)

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
    meta = {"date": date_str}
    out = render_html(diagram_html, pairs, meta)

    out_path = Path(__file__).resolve().parent.parent / "reports" / f"test-report-e2e-{date_str}.html"
    out_path.write_text(out, encoding="utf-8")
    print(f"\nReporte escrito en: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
