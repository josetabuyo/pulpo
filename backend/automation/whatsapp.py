"""
WhatsAppSession — automatización de WhatsApp Web.

Hereda de BrowserAutomation y agrega los métodos específicos de WhatsApp Web:
  - connect()         → intenta restaurar sesión; si no, navega y pide QR
  - get_qr()          → captura el canvas del QR como PNG base64
  - wait_for_auth()   → espera que el usuario escanee el QR; guarda sesión en disco
  - is_connected()    → verifica si la sesión está autenticada y activa
  - send_message()    → envía un mensaje a un número

Regla de oro: el auth state en disco NUNCA se borra ni sobreescribe
excepto tras una autenticación exitosa confirmada (wait_for_auth).
"""

import base64
import logging
from pathlib import Path

from automation.browser import BrowserAutomation
from state import clients

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("data/sessions")
WA_URL = "https://web.whatsapp.com/"

# Timeouts
QR_APPEAR_TIMEOUT_MS  = 30_000   # tiempo máximo para que aparezca el QR
QR_SCAN_TIMEOUT_MS    = 120_000  # tiempo máximo para que el usuario escanee
SEND_TIMEOUT_MS       = 15_000


class WhatsAppSession(BrowserAutomation):
    """
    Una instancia de esta clase gestiona TODAS las sesiones de WhatsApp
    del servidor (una pestaña por teléfono, dentro del mismo browser).
    """

    def _storage_path(self, session_id: str) -> Path:
        return SESSIONS_DIR / session_id / "storage.json"

    # ------------------------------------------------------------------
    # Conexión — punto de entrada principal
    # ------------------------------------------------------------------

    async def connect(self, session_id: str, bot_id: str) -> str:
        """
        Intenta conectar la sesión:
          1. Si hay auth state en disco → lo carga y verifica si sigue activo.
          2. Si no hay estado o caducó → navega a WA Web y espera el QR.

        Retorna:
          "restored"   → sesión restaurada, no necesita QR
          "qr_needed"  → hay que mostrar QR al usuario
          "failed"     → error inesperado
        """
        _update(session_id, bot_id=bot_id, status="connecting")

        try:
            storage = self._storage_path(session_id)
            page = await self.open_session(session_id, storage_path=storage)
            await page.goto(WA_URL, wait_until="domcontentloaded")

            # Damos hasta 8 segundos para detectar si ya está autenticado
            # (el QR no aparece = estamos dentro)
            try:
                await page.wait_for_selector(
                    "canvas[aria-label], div[data-ref]",
                    timeout=8_000,
                )
                # Apareció el QR → sesión caducada o primera vez
                _update(session_id, status="qr_needed")
                logger.info(f"[{session_id}] QR requerido.")
                return "qr_needed"

            except Exception:
                # No apareció el QR → ya estamos autenticados
                _update(session_id, status="ready")
                logger.info(f"[{session_id}] Sesión restaurada correctamente.")
                return "restored"

        except Exception as e:
            logger.error(f"[{session_id}] Error al conectar: {e}")
            _update(session_id, status="failed")
            return "failed"

    # ------------------------------------------------------------------
    # QR
    # ------------------------------------------------------------------

    async def get_qr(self, session_id: str) -> str | None:
        """
        Captura el canvas del QR como PNG base64.
        Solo llamar cuando connect() retornó "qr_needed".
        """
        page = self.get_page(session_id)
        if not page:
            logger.warning(f"[{session_id}] get_qr: no hay página abierta")
            return None
        try:
            canvas = page.locator("canvas").first
            await canvas.wait_for(state="visible", timeout=QR_APPEAR_TIMEOUT_MS)
            qr_bytes = await canvas.screenshot(type="png")
            qr_b64 = "data:image/png;base64," + base64.b64encode(qr_bytes).decode()
            _update(session_id, status="qr_ready", qr=qr_b64)
            logger.info(f"[{session_id}] QR capturado.")
            return qr_b64
        except Exception as e:
            logger.error(f"[{session_id}] Error capturando QR: {e}")
            _update(session_id, status="failed")
            return None

    async def wait_for_auth(self, session_id: str) -> bool:
        """
        Espera hasta que el usuario escanee el QR.
        Cuando se autentica, guarda el auth state en disco inmediatamente.
        Retorna True si se autenticó, False si venció el timeout.
        """
        page = self.get_page(session_id)
        if not page:
            return False
        try:
            # El QR desaparece cuando el usuario lo escanea
            await page.wait_for_selector(
                "canvas[aria-label], div[data-ref]",
                state="hidden",
                timeout=QR_SCAN_TIMEOUT_MS,
            )
            # Guardar sesión en disco INMEDIATAMENTE tras autenticación exitosa
            await self.save_session(session_id, self._storage_path(session_id))
            _update(session_id, status="ready", qr=None)
            logger.info(f"[{session_id}] Autenticado y sesión guardada en disco.")
            return True
        except Exception:
            logger.warning(f"[{session_id}] Timeout esperando scan del QR.")
            _update(session_id, status="qr_needed")
            return False

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    async def is_connected(self, session_id: str) -> bool:
        """True si la página existe, responde, y no está mostrando el QR."""
        if not await self.is_page_alive(session_id):
            return False
        page = self.get_page(session_id)
        try:
            qr = await page.query_selector("canvas[aria-label], div[data-ref]")
            return qr is None
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Envío de mensajes
    # ------------------------------------------------------------------

    async def send_message(self, session_id: str, phone: str, text: str) -> bool:
        """
        Envía un mensaje de texto a un número vía WhatsApp Web.
        phone: número sin +, ej. "5491155612767"
        """
        page = self.get_page(session_id)
        if not page:
            logger.warning(f"[{session_id}] send_message: no hay página activa")
            return False
        try:
            url = f"https://web.whatsapp.com/send?phone={phone}&text={text}"
            await page.goto(url, wait_until="domcontentloaded")
            send_btn = page.locator("[data-testid='send'], [aria-label='Enviar']")
            await send_btn.wait_for(state="visible", timeout=SEND_TIMEOUT_MS)
            await send_btn.click()
            logger.info(f"[{session_id}] Mensaje enviado a {phone}")
            return True
        except Exception as e:
            logger.error(f"[{session_id}] Error enviando mensaje a {phone}: {e}")
            return False


# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------

def _update(session_id: str, *, bot_id: str = "", status: str, qr: str | None = None) -> None:
    if session_id not in clients:
        clients[session_id] = {"bot_id": bot_id, "type": "whatsapp", "client": None, "qr": None}
    if bot_id:
        clients[session_id]["bot_id"] = bot_id
    clients[session_id]["status"] = status
    if qr is not None or status in ("connecting", "failed", "ready"):
        clients[session_id]["qr"] = qr
