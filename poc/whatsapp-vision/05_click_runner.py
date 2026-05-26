"""
05_click_runner.py — Ejecuta los clicks sobre los mensajes que lo requieren.

Flujo por bubble (orden: id=1 primero = más nuevo):
  1. Lee _bubbles.json del último run del pipeline
  2. Filtra audio y file (tienen click_point)
  3. Para cada uno:
       a. click en click_point (▶ para audio, descarga para file)
       b. espera breve
       c. screenshot nuevo
       d. re-detecta bubbles para ver qué cambió
  4. Reporta resultado

Uso:
  python 05_click_runner.py <bubbles_json> <profile_dir>

  bubbles_json  → assets/luiz_fernando_pita_bubbles.json
  profile_dir   → data/poc_profile/  (copia del perfil de producción)

ANTES DE CORRER:
  cp -r /ruta/al/perfil/produccion  poc-whatsapp-vision/data/poc_profile/
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from wa_driver import WADriver
from element_detector import detect_bubbles
from PIL import Image

ASSETS = Path(__file__).parent / "assets"


def load_bubbles(json_path: Path) -> list[dict]:
    with open(json_path) as f:
        data = json.load(f)
    # Solo los que requieren acción, ordenados id ascendente (más nuevo primero)
    actionable = [b for b in data if b.get("click_point") is not None]
    actionable.sort(key=lambda b: b["id"])
    return actionable


def redetect(screenshot_path: Path) -> int:
    """Corre detección de burbujas sobre el screenshot y retorna la cantidad."""
    img = Image.open(screenshot_path)
    bubbles = detect_bubbles(img, footer_px=70)
    return len(bubbles)


async def run(bubbles_json: Path, profile_dir: Path) -> None:
    bubbles = load_bubbles(bubbles_json)
    print(f"\n{len(bubbles)} bubbles con acción pendiente")
    for b in bubbles:
        print(f"  #{b['id']:2d} [{b['sender']:5s}] {b['msg_type']:6s}  "
              f"click_point={b['click_point']}  ts={b['timestamp']}")

    if not bubbles:
        print("Nada que hacer.")
        return

    driver = WADriver(profile_dir=profile_dir, headless=False)
    await driver.connect()

    # Confirmar que el viewport está en el chat correcto antes de empezar
    input("\n[?] Confirmá que el chat está abierto y visible → Enter para continuar: ")

    results = []
    for b in bubbles:
        bid   = b["id"]
        btype = b["msg_type"]
        cp    = b["click_point"]
        cx, cy = cp["x"], cp["y"]

        print(f"\n── #{bid} {btype} ──")

        if btype == "file":
            dl_path = await driver.download(cx, cy)
            result = {"id": bid, "type": btype, "downloaded": str(dl_path)}
        else:
            # audio → click play, luego screenshot para ver si el player abrió
            await driver.click(cx, cy)
            await driver.wait(1500)
            shot = await driver.screenshot(name=f"after_click_{bid}")
            n_bubbles = redetect(shot)
            result = {"id": bid, "type": btype, "screenshot": shot.name,
                      "bubbles_after": n_bubbles}

        results.append(result)
        print(f"   → {result}")

    print("\n\n══ RESUMEN ══")
    for r in results:
        print(f"  #{r['id']:2d}  {r}")

    await driver.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python 05_click_runner.py <bubbles.json> <profile_dir>")
        sys.exit(1)
    asyncio.run(run(Path(sys.argv[1]), Path(sys.argv[2])))
