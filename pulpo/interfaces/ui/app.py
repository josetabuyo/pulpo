import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, auth_bot, client, bot_portal
from pulpo.interfaces.api.app import create_api_app
from pulpo.interfaces.ui.deps import require_admin, require_client
from pulpo.core.lifespan import pulpo_lifespan


def create_ui_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(title="Pulpo UI", version="0.1.0", lifespan=pulpo_lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok"}

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
