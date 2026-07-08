import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, auth_bot, client, bot_portal
from pulpo.interfaces.api.app import create_api_app
from pulpo.interfaces.ui.deps import require_admin, require_client
from pulpo.core.lifespan import pulpo_lifespan


class _PollFilter(logging.Filter):
    """Baja a DEBUG las rutas de polling frecuente para no saturar el log."""
    _SKIP = ("/api/logs/latest", "/api/bots")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(p in msg for p in self._SKIP):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
            return False  # la descarta del handler INFO
        return True


class _UpdaterPollingFilter(logging.Filter):
    """
    El Updater de python-telegram-bot reintenta getUpdates solo ante fallas de red
    (comportamiento esperado, se recupera solo — Telegram retiene los updates pendientes),
    pero loguea el traceback completo en CADA intento. Con reintentos cada pocos segundos
    eso vuelve el log ilegible y no deja ver cuándo empezó ni cuánto duró una caída real.

    Colapsamos la racha: traceback completo solo en el primer fallo, resumen liviano
    después con contador y duración — así queda claro el inicio y el largo del incidente
    sin perder la señal en ruido.
    """
    _STREAK_RESET_AFTER = 30  # segundos sin fallos → se considera una racha nueva

    def __init__(self):
        super().__init__()
        self._streak_start = None
        self._streak_count = 0
        self._last_fail = None

    def filter(self, record: logging.LogRecord) -> bool:
        if "Exception happened while polling for updates" not in record.getMessage():
            return True

        import time
        now = time.monotonic()
        new_streak = self._streak_start is None or (
            self._last_fail is not None and now - self._last_fail > self._STREAK_RESET_AFTER
        )
        if new_streak:
            self._streak_start = now
            self._streak_count = 0
        self._streak_count += 1
        self._last_fail = now

        if not new_streak:
            record.exc_info = None
            record.exc_text = None
            record.msg = (
                f"Sigue sin conexión a Telegram — intento #{self._streak_count}, "
                f"caído hace {now - self._streak_start:.0f}s (ver traceback completo en el primer fallo de la racha)"
            )
            record.args = ()
        return True


logger = logging.getLogger(__name__)


def create_ui_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    )

    # httpx loguea en INFO cada request HTTP (getUpdates, etc.) — no nos aporta nada
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Las rutas de polling frecuente no deben aparecer en los logs de INFO
    logging.getLogger("uvicorn.access").addFilter(_PollFilter())

    # Colapsar el spam de tracebacks de reconexión de Telegram (ver docstring del filtro)
    logging.getLogger("telegram.ext.Updater").addFilter(_UpdaterPollingFilter())

    app = FastAPI(title="Pulpo UI", version="0.1.0", lifespan=pulpo_lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.middleware("http")
    async def log_404_origin(request, call_next):
        response = await call_next(request)
        if response.status_code == 404:
            logger.warning(
                "[404] %s %s — client=%s origin=%s referer=%s user-agent=%s",
                request.method, request.url.path,
                request.client.host if request.client else "?",
                request.headers.get("origin", "-"),
                request.headers.get("referer", "-"),
                request.headers.get("user-agent", "-"),
            )
        return response

    frontend_port = os.environ.get("FRONTEND_PORT", "5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://localhost:{frontend_port}"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth routes bajo /api para que el proxy de Vite (/api → backend) funcione
    app.include_router(auth.router, prefix="/api")
    app.include_router(auth_bot.router, prefix="/api")
    app.include_router(client.router, prefix="/api")
    app.include_router(bot_portal.router, prefix="/api")

    # Mount the API under /api — Depends(require_admin) or bearer token protects individual routes
    # Each api router applies its own deps via the UI-aware wrappers
    api = create_api_app()
    app.mount("/api", api)

    return app
