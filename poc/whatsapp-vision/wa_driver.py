"""
wa_driver.py — Driver Playwright mínimo para el POC de visión.

Responsabilidades:
  - screenshot()          → captura el viewport actual → Path
  - click(x, y)           → click en coordenadas del panel recortado
  - download(x, y)        → click + captura de descarga → Path
  - close()               → cierra el browser limpiamente

Contrato de coordenadas:
  x, y están en espacio del PANEL RECORTADO (sin sidebar).
  El driver suma el sidebar_x internamente antes de clickear.
  DPR=1 (Playwright sin device_scale_factor → 1:1 CSS pixels).

Conexión:
  Usa launch_persistent_context() con una COPIA del perfil de producción.
  → Copiar antes de usar:
      cp -r data/sessions/<número>/profile/  data/poc_profile/
  Así reutilizamos la sesión WA sin tocar el perfil de producción.

  TODO (último paso): llamar connect() con el profile_dir correcto.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
DOWNLOADS = Path(__file__).parent / "downloads"
DOWNLOADS.mkdir(exist_ok=True)

# Sidebar offset medido en el pipeline (px en el screenshot 1280px)
SIDEBAR_X = 580


class WADriver:
    def __init__(self, profile_dir: str | Path, headless: bool = False):
        self.profile_dir = str(profile_dir)
        self.headless = headless
        self._pw = None
        self._context = None
        self._page = None

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Lanza el browser con el perfil persistente y navega a WhatsApp Web."""
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="es-AR",
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

        if "web.whatsapp.com" not in self._page.url:
            await self._page.goto("https://web.whatsapp.com")

        # Esperar a que cargue el chat (o el QR si la sesión expiró)
        await self._page.wait_for_load_state("domcontentloaded")
        print(f"[driver] conectado → {self._page.url}")

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()

    # ── Acciones ──────────────────────────────────────────────────────────────

    async def screenshot(self, name: str = "current") -> Path:
        """Captura el viewport completo. Retorna el path del archivo."""
        out = ASSETS / f"{name}.png"
        await self._page.screenshot(path=str(out), full_page=False)
        print(f"[driver] screenshot → {out.name}")
        return out

    async def click(self, crop_x: int, crop_y: int) -> None:
        """Click en coordenadas del panel recortado (sin sidebar)."""
        vx = crop_x + SIDEBAR_X
        vy = crop_y
        await self._page.mouse.click(vx, vy)
        print(f"[driver] click crop({crop_x},{crop_y}) → viewport({vx},{vy})")

    async def download(self, crop_x: int, crop_y: int,
                       timeout: int = 15_000) -> Path | None:
        """Click con espera de descarga. Retorna el path del archivo descargado."""
        vx = crop_x + SIDEBAR_X
        vy = crop_y
        async with self._page.expect_download(timeout=timeout) as dl_info:
            await self._page.mouse.click(vx, vy)
        dl = await dl_info.value
        dest = DOWNLOADS / dl.suggested_filename
        await dl.save_as(str(dest))
        print(f"[driver] descargado → {dest.name}")
        return dest

    async def wait(self, ms: int = 1500) -> None:
        await asyncio.sleep(ms / 1000)
