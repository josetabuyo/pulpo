#!/usr/bin/env python3
"""
POC — Mini Browser Driver con sesión WA real.

Uso:
    ./venv/bin/python 05_capture_live.py "Luiz Fernando Pita"   # headless por defecto
    ./venv/bin/python 05_capture_live.py "Fabian Miranda" --headed

⚠️  Este script para brevemente la sesión WA del bot. El bot reconecta solo.
    NUNCA modificar data/sessions/5491155612767/profile/ directamente.
"""

import asyncio
import shutil
import sys
import glob
from pathlib import Path

from playwright.async_api import async_playwright

# ── Config ────────────────────────────────────────────────────────────────────
ORIGINAL_PROFILE = Path("/Users/josetabuyo/Development/pulpo/_/backend/data/sessions/5491155612767/profile")
POC_PROFILE      = Path(__file__).parent / "session_copy" / "profile"
ASSETS           = Path(__file__).parent / "assets"
CONTACT          = sys.argv[1] if len(sys.argv) > 1 else "Luiz Fernando Pita"
HEADLESS         = "--headed" not in sys.argv  # headless by default


def clean_assets():
    for f in ASSETS.glob("*"):
        f.unlink()


# ── Mini Driver ───────────────────────────────────────────────────────────────

class MiniDriver:
    def __init__(self, page):
        self._page = page

    async def screenshot(self) -> bytes:
        return await self._page.screenshot(type="png", full_page=False)

    async def click(self, x: int, y: int):
        await self._page.mouse.click(x, y)

    async def scroll(self, dy: int):
        await self._page.mouse.wheel(0, dy)

    async def type(self, text: str, delay: int = 80):
        await self._page.keyboard.type(text, delay=delay)

    async def key(self, key: str):
        await self._page.keyboard.press(key)

    async def wait(self, ms: int):
        await self._page.wait_for_timeout(ms)

    async def save_screenshot(self, path: str | Path) -> Path:
        data = await self.screenshot()
        p = Path(path)
        p.write_bytes(data)
        return p


# ── Flujo de captura ──────────────────────────────────────────────────────────

async def capture_chat(contact: str, headless: bool = True) -> Path:
    print(f"\n{'='*60}")
    print(f"Mini Driver — WA Vision Capture")
    print(f"Contacto : {contact}")
    print(f"Modo     : {'headless' if headless else 'HEADED (visible)'}")
    print(f"{'='*60}\n")

    clean_assets()

    if POC_PROFILE.exists():
        shutil.rmtree(POC_PROFILE)
    print("[1/5] Copiando perfil de sesión WA…")
    shutil.copytree(ORIGINAL_PROFILE, POC_PROFILE)

    async with async_playwright() as pw:
        print("[2/5] Abriendo Chromium…")
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(POC_PROFILE),
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 4000},
            locale="es-AR",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.pages[0] if context.pages else await context.new_page()
        driver = MiniDriver(page)

        print("[3/5] Navegando a WA Web…")
        await page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=30_000)
        await driver.wait(2000)

        use_here = page.locator('button:has-text("Usar aquí")')
        if await use_here.count() > 0:
            await use_here.click()
            await driver.wait(3000)

        print("      → Esperando lista de chats…")
        await page.wait_for_selector('[data-testid="chat-list"]', timeout=25_000)

        print(f"[4/5] Buscando '{contact}'…")
        search_box = page.locator('[data-testid="chat-list-search-container"]')
        bbox = await search_box.bounding_box()
        if bbox:
            await driver.click(int(bbox["x"] + bbox["width"] / 2), int(bbox["y"] + bbox["height"] / 2))
        await driver.wait(700)
        await driver.type(contact)
        await driver.wait(2500)

        # Buscar el resultado cuyo título contenga el nombre del contacto
        cells = page.locator('[data-testid="cell-frame-container"]')
        count = await cells.count()
        clicked = False
        for i in range(min(count, 5)):
            cell = cells.nth(i)
            title = cell.locator('[data-testid="cell-frame-title"]')
            cell_text = await title.inner_text() if await title.count() > 0 else ""
            first_word = contact.split()[0].lower()
            if first_word in cell_text.lower():
                bbox = await cell.bounding_box()
                if bbox:
                    await driver.click(int(bbox["x"] + bbox["width"] / 2), int(bbox["y"] + bbox["height"] / 2))
                    clicked = True
                    print(f"      → Abriendo: '{cell_text}'")
                    break

        if not clicked:
            print(f"      ⚠️  No encontré '{contact}', abriendo primer resultado")
            first = cells.first
            bbox = await first.bounding_box()
            if bbox:
                await driver.click(int(bbox["x"] + bbox["width"] / 2), int(bbox["y"] + bbox["height"] / 2))

        print("      → Esperando que el chat se abra…")
        try:
            await page.wait_for_selector('[data-testid="conversation-header"]', timeout=10_000)
            # Verificar que el header muestra el contacto correcto
            header = page.locator('[data-testid="conversation-header"]')
            header_text = await header.inner_text()
            print(f"      → Header: '{header_text[:50]}'")
            await driver.wait(2000)
        except Exception:
            print("      ⚠️  Timeout esperando el chat")
            await driver.save_screenshot(ASSETS / "debug.png")
            await context.close()
            return ASSETS / "debug.png"

        print("[5/5] Capturando screenshot…")
        slug = contact.lower().replace(" ", "_")
        out = ASSETS / f"{slug}.png"
        await driver.save_screenshot(out)
        print(f"      → {out.name}")
        await context.close()

    return out


async def main():
    out = await capture_chat(CONTACT, headless=HEADLESS)
    print("\n[+] Corriendo pipeline de visión…")
    import subprocess
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "04_full_pipeline.py"), str(out)],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)


if __name__ == "__main__":
    asyncio.run(main())
