"""
BrowserAutomation — herramienta genérica de automatización web.

Cada método público es una automatización fija (no configurable por el usuario).
Usa Playwright en modo headless para ejecutar las acciones.

Automatizaciones disponibles:
  - whatsapp_get_qr(session_id): abre WhatsApp Web, captura el QR y lo guarda en state.
"""

import asyncio
import base64
import logging
from playwright.async_api import async_playwright, Page, Browser

from state import clients

logger = logging.getLogger(__name__)

# Cuánto tiempo máximo esperar el QR antes de abortar (segundos)
QR_TIMEOUT_MS = 60_000


class BrowserAutomation:
    """
    Automatizaciones web fijas implementadas con Playwright.
    Instanciar una vez y reutilizar, o usar directamente los métodos estáticos/async.
    """

    # ------------------------------------------------------------------
    # WhatsApp — Vincular QR
    # ------------------------------------------------------------------

    async def whatsapp_get_qr(self, session_id: str) -> None:
        """
        Abre WhatsApp Web, espera el canvas del QR, lo captura como PNG base64
        y actualiza state.clients[session_id].

        Estados que escribe en state:
          - "connecting"  → mientras navega
          - "qr_ready"    → QR capturado y disponible en state["qr"]
          - "failed"      → si no aparece el QR en el tiempo esperado
        """
        _set_state(session_id, status="connecting", qr=None)
        logger.info(f"[{session_id}] Iniciando automatización WhatsApp Web...")

        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(headless=True)
            try:
                page: Page = await browser.new_page()
                await page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")

                # WhatsApp renderiza el QR en un <canvas> dentro de un div con data-ref
                # Esperamos hasta que aparezca
                logger.info(f"[{session_id}] Esperando QR canvas en WhatsApp Web...")
                qr_canvas = page.locator("canvas").first
                await qr_canvas.wait_for(state="visible", timeout=QR_TIMEOUT_MS)

                # Capturamos solo el canvas como PNG
                qr_bytes = await qr_canvas.screenshot(type="png")
                qr_b64 = "data:image/png;base64," + base64.b64encode(qr_bytes).decode()

                _set_state(session_id, status="qr_ready", qr=qr_b64)
                logger.info(f"[{session_id}] QR capturado correctamente.")

            except Exception as e:
                logger.error(f"[{session_id}] Error capturando QR: {e}")
                _set_state(session_id, status="failed", qr=None)
            finally:
                await browser.close()


# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------

def _set_state(session_id: str, status: str, qr: str | None) -> None:
    if session_id not in clients:
        clients[session_id] = {"bot_id": "", "type": "whatsapp", "client": None}
    clients[session_id]["status"] = status
    clients[session_id]["qr"] = qr
