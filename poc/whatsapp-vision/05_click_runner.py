"""
05_click_runner.py — Ejecuta los clicks via el backend Pulpo (sesión WA ya activa).

Flujo:
  1. capture-chat  → navega al contacto y toma screenshot
  2. pipeline      → detecta bubbles, clasifica, calcula click_points
  3. por cada audio/file (orden id=1 primero = más nuevo):
       a. POST /poc/click/{session_id}  con coords viewport (crop_x + sidebar_x)
       b. screenshot guardado en assets/after_click_{id}.png
  4. reporte final

Uso:
  python 05_click_runner.py <session_id> <contact_name>

  session_id   → número de teléfono, ej: 5491155612767
  contact_name → nombre exacto como aparece en WA, ej: "Luis Fernando Pita"
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ASSETS    = Path(__file__).parent / "assets"
BACKEND   = "http://localhost:8000"
SIDEBAR_X = 580   # medido en el pipeline
HEADER_Y  =  60   # header WA recortado en crop_chat_panel
AUTH      = {"x-password": "MonoLoco"}

# ── Helpers HTTP ──────────────────────────────────────────────────────────────

def _get(path: str) -> dict:
    req = urllib.request.Request(f"{BACKEND}{path}", headers=AUTH)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(f"{BACKEND}{path}", data=data,
                                  headers={"Content-Type": "application/json", **AUTH})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

# ── Steps ─────────────────────────────────────────────────────────────────────

def step_capture(session_id: str, contact: str) -> Path:
    """Navega al chat y guarda el screenshot en assets/."""
    out = str(ASSETS / "current.png")
    encoded = urllib.parse.quote(contact)
    print(f"[1] capture-chat → {contact}")
    _get(f"/api/capture-chat/{session_id}?contact={encoded}&out={out}")
    return Path(out)

def step_pipeline(screenshot: Path) -> list[dict]:
    """Corre el pipeline y retorna los bubbles con click_point."""
    print(f"[2] pipeline → {screenshot.name}")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "04_full_pipeline.py"), str(screenshot)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("pipeline falló")
    bubbles_json = ASSETS / (screenshot.stem + "_bubbles.json")
    bubbles = json.loads(bubbles_json.read_text())
    actionable = [b for b in bubbles if b.get("click_point")]
    actionable.sort(key=lambda b: b["id"])   # id=1 primero (más nuevo)
    print(f"   {len(bubbles)} bubbles detectados  |  {len(actionable)} con acción")
    return actionable

def step_click(session_id: str, bubble: dict) -> Path:
    """Ejecuta el click y guarda el screenshot post-click."""
    cp  = bubble["click_point"]
    vx  = cp["x"] + SIDEBAR_X
    vy  = cp["y"] + HEADER_Y
    out = str(ASSETS / f"after_click_{bubble['id']}.png")
    print(f"   click #{bubble['id']:2d} {bubble['msg_type']:6s} "
          f"crop({cp['x']},{cp['y']}) → viewport({vx},{vy})")
    _post(f"/api/poc/click/{session_id}",
          {"x": vx, "y": vy, "wait_ms": 2000, "out": out})
    return Path(out)

# ── Main ──────────────────────────────────────────────────────────────────────

def run(session_id: str, contact: str) -> None:
    ASSETS.mkdir(exist_ok=True)
    # Limpiar assets generados antes de cada run — nunca confiar en datos viejos
    subprocess.run([str(Path(__file__).parent / "clean.sh")], check=True)

    screenshot  = step_capture(session_id, contact)
    actionable  = step_pipeline(screenshot)

    if not actionable:
        print("Sin acciones pendientes.")
        return

    print(f"\n[3] ejecutando {len(actionable)} clicks…")
    results = []
    for b in actionable:
        try:
            shot = step_click(session_id, b)
            results.append({"id": b["id"], "type": b["msg_type"],
                            "ts": b["timestamp"], "shot": shot.name, "ok": True})
        except Exception as e:
            results.append({"id": b["id"], "type": b["msg_type"], "ok": False, "error": str(e)})

    print("\n══ RESUMEN ══")
    for r in results:
        status = "✓" if r["ok"] else "✗"
        print(f"  {status} #{r['id']:2d} {r['type']:6s}  ts={r.get('ts')}  → {r.get('shot', r.get('error'))}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python 05_click_runner.py <session_id> <contact_name>")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
