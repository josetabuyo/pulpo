"""
BrowserAutomation — base genérica de automatización web con Playwright.

Gestiona un único proceso de browser con múltiples contextos aislados,
uno por sesión. Cada contexto tiene su propia página y su propio storage
(cookies, localStorage), lo que permite manejar N sesiones en paralelo.

No contiene lógica de ningún sitio específico. Las subclases (ej. WhatsAppSession)
agregan los métodos propios de cada servicio.
"""

import logging
from pathlib import Path
from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
)

logger = logging.getLogger(__name__)


class BrowserAutomation:
    """
    Gestiona un browser compartido y N contextos (sesiones) aislados.

    Uso típico:
        ba = BrowserAutomation(headless=False)  # False para debug visual
        await ba.launch()
        page = await ba.open_session("mi-sesion", storage_path="data/sessions/mi-sesion/storage.json")
        ...
        await ba.shutdown()
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        # session_id → contexto y página activos
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}

    # ------------------------------------------------------------------
    # Ciclo de vida del browser
    # ------------------------------------------------------------------

    async def launch(self) -> None:
        """Inicia el proceso de browser. Llamar una vez al arrancar la app."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        logger.info(f"Browser iniciado (headless={self.headless})")

    async def ensure_launched(self) -> None:
        """Verifica que el browser esté vivo; si se cayó, lo relanza."""
        try:
            if self._browser and self._browser.is_connected():
                return
        except Exception:
            pass
        logger.warning("Browser no disponible, relanzando...")
        await self.launch()

    async def shutdown(self) -> None:
        """Cierra el browser. NO borra los archivos de sesión en disco."""
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        logger.info("Browser cerrado.")

    # ------------------------------------------------------------------
    # Gestión de sesiones
    # ------------------------------------------------------------------

    async def open_session(
        self,
        session_id: str,
        storage_path: str | Path | None = None,
    ) -> Page:
        """
        Abre un nuevo contexto aislado para session_id.
        Si storage_path existe en disco, lo carga (restaura sesión previa).
        Si ya hay un contexto abierto para ese session_id, lo devuelve directamente.
        """
        if session_id in self._pages:
            logger.info(f"[{session_id}] Contexto ya abierto, reutilizando.")
            return self._pages[session_id]

        kwargs: dict = {}
        if storage_path and Path(storage_path).exists():
            kwargs["storage_state"] = str(storage_path)
            logger.info(f"[{session_id}] Restaurando sesión desde {storage_path}")
        else:
            logger.info(f"[{session_id}] Abriendo contexto nuevo (sin sesión previa)")

        context = await self._browser.new_context(**kwargs)
        page = await context.new_page()

        self._contexts[session_id] = context
        self._pages[session_id] = page
        return page

    async def save_session(self, session_id: str, storage_path: str | Path) -> None:
        """
        Persiste el auth state (cookies + localStorage) en disco.
        Llamar solo tras una autenticación exitosa confirmada.
        NUNCA llamar en paths de error.
        """
        context = self._contexts.get(session_id)
        if not context:
            logger.warning(f"[{session_id}] save_session: no hay contexto abierto")
            return
        path = Path(storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(path))
        logger.info(f"[{session_id}] Sesión guardada en {path}")

    async def close_session(self, session_id: str) -> None:
        """
        Cierra el contexto en memoria. NO toca los archivos en disco.
        El auth state guardado anteriormente sigue intacto para la próxima vez.
        """
        context = self._contexts.pop(session_id, None)
        self._pages.pop(session_id, None)
        if context:
            await context.close()
            logger.info(f"[{session_id}] Contexto cerrado (archivo de sesión intacto).")

    def get_page(self, session_id: str) -> Page | None:
        return self._pages.get(session_id)

    def active_sessions(self) -> list[str]:
        return list(self._pages.keys())

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def is_page_alive(self, session_id: str) -> bool:
        """Devuelve True si la página está abierta y responde."""
        page = self._pages.get(session_id)
        if not page or page.is_closed():
            return False
        try:
            await page.evaluate("1")
            return True
        except Exception:
            return False
