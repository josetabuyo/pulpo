"""
Router: /runs

Thin FastAPI wrapper sobre el journal de ejecuciones de flows (ADR-006).
No auth — auth la aplica interfaces/ui/app.py al montar.

Route layout (parent mounts at /runs):
  GET /bots/{bot_id}          — últimas N ejecuciones de una bot
  GET /{run_id}               — detalle de un run con sus steps
"""
import logging

from fastapi import APIRouter, HTTPException, Query

from pulpo.core import db

_log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/bots/{bot_id}")
async def list_runs(bot_id: str, limit: int = Query(50, ge=1, le=500)):
    """Lista las últimas ejecuciones de flows de una bot, más recientes primero."""
    return await db.get_flow_runs(bot_id, limit=limit)


@router.get("/{run_id}")
async def get_run(run_id: str):
    """Detalle de una ejecución: metadata del run + todos sus steps con input/output."""
    run = await db.get_flow_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    run["steps"] = await db.get_flow_run_steps(run_id)
    return run
