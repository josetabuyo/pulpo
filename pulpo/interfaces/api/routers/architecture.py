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

from pulpo.business import architecture as architecture_svc

logger = logging.getLogger(__name__)

router = APIRouter()

# architecture.py vive en pulpo/interfaces/api/routers/ → subir 5 niveles llega a _/ (worktree root)
_ROOT = Path(__file__).parent.parent.parent.parent.parent
_MONITOR = _ROOT / "monitor"


@router.get("")
async def get_architecture(request: Request) -> dict:
    routes = [
        {
            "path": r.path,
            "methods": sorted(m for m in r.methods if m != "HEAD"),
            "name": r.name,
        }
        for r in request.app.routes
        if isinstance(r, APIRoute)
    ]

    try:
        return await architecture_svc.get_architecture(
            routes=routes,
            monitor_dir=_MONITOR,
            root_dir=_ROOT,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
