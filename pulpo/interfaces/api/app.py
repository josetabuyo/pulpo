from fastapi import FastAPI
from .routers import bots, connections, flows, messages, contacts, settings, sim, wavi, logs, architecture, runs


def create_api_app() -> FastAPI:
    app = FastAPI(title="Pulpo API", version="0.1.0")
    app.include_router(bots.router, prefix="/bots", tags=["bots"])
    app.include_router(connections.router, prefix="/connections", tags=["connections"])
    app.include_router(flows.router, prefix="/flows", tags=["flows"])
    app.include_router(messages.router, prefix="/messages", tags=["messages"])
    app.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
    app.include_router(settings.router, prefix="/settings", tags=["settings"])
    app.include_router(sim.router, prefix="/sim", tags=["sim"])
    app.include_router(wavi.router, prefix="/wavi", tags=["wavi"])
    app.include_router(logs.router, prefix="/logs", tags=["logs"])
    app.include_router(architecture.router, prefix="/architecture", tags=["architecture"])
    app.include_router(runs.router, prefix="/runs", tags=["runs"])
    # node-types and other flow meta-routes are on flows router at /flows/...
    return app
