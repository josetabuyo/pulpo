"""
Router: /logs

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Route layout (parent mounts at /logs):
  GET /latest   (query: source, lines)
  GET /stream   (query: source) — SSE stream
"""
import asyncio
import json
import os
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter()

# logs.py vive en pulpo/interfaces/api/routers/ → subir 5 niveles llega a _/ (worktree root)
_PROJECT_DIR = Path(__file__).parent.parent.parent.parent.parent
_MONITORING_JSON = _PROJECT_DIR / "monitoring.json"


def _load_monitoring_config() -> dict:
    try:
        with open(_MONITORING_JSON, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="monitoring.json no encontrado")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"monitoring.json malformado: {e}")


def _resolve_log_path(source: str) -> str:
    config = _load_monitoring_config()
    sources = config.get("log_sources", {})
    if source not in sources:
        raise HTTPException(status_code=400, detail=f"Fuente desconocida: {source}")
    rel_path = sources[source]
    return str(_PROJECT_DIR / rel_path)


@router.get("/latest")
async def logs_latest(
    source: str = Query("backend"),
    lines: int = Query(200, ge=1, le=5000),
):
    path = _resolve_log_path(source)
    if not os.path.exists(path):
        return {"lines": [], "source": source}

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            buf = deque(f, maxlen=lines)
        return {"lines": list(buf), "source": source}
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream")
async def logs_stream(source: str = Query("backend")):
    path = _resolve_log_path(source)

    async def event_generator():
        while not os.path.exists(path):
            yield "data: [esperando log...]\n\n"
            await asyncio.sleep(1)

        with open(path, encoding="utf-8", errors="replace") as f:
            # Posicionarse al final
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
