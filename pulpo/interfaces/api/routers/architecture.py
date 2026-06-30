"""
Router: /architecture

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Route layout (parent mounts at /architecture):
  GET /   → radiografía viva del sistema
"""
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute
from starlette.routing import Mount

from pulpo.business import architecture as architecture_svc

logger = logging.getLogger(__name__)

router = APIRouter()

# architecture.py vive en pulpo/interfaces/api/routers/ → subir 5 niveles llega a _/ (worktree root)
_ROOT = Path(__file__).parent.parent.parent.parent.parent
_MONITOR = _ROOT / "monitor"


def _collect_routes(route_list, prefix: str = "") -> list[dict]:
    """Walk the route tree recursively.

    Handles both classic APIRoute instances and _IncludedRouter wrappers
    introduced in FastAPI >= 0.115.
    """
    result = []
    for r in route_list:
        if isinstance(r, APIRoute):
            result.append({
                "path": prefix + r.path,
                "methods": sorted(m for m in r.methods if m != "HEAD"),
                "name": r.name,
            })
        elif isinstance(r, Mount) and hasattr(r, "app") and hasattr(r.app, "routes"):
            result.extend(_collect_routes(r.app.routes, prefix + (r.path or "")))
        elif hasattr(r, "include_context") and hasattr(r, "original_router"):
            # _IncludedRouter — FastAPI >= 0.115 lazy router wrapper
            ctx_prefix = getattr(r.include_context, "prefix", "")
            result.extend(_collect_routes(r.original_router.routes, prefix + ctx_prefix))
    return result


@router.get("")
async def get_architecture(request: Request) -> dict:
    # root_path holds the mount prefix set by the parent app (e.g. "/api")
    mount_prefix = request.scope.get("root_path", "")
    routes = _collect_routes(request.app.routes, prefix=mount_prefix)

    try:
        return await architecture_svc.get_architecture(
            routes=routes,
            monitor_dir=_MONITOR,
            root_dir=_ROOT,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
