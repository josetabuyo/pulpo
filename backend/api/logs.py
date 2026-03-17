import json
import os
from collections import deque
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import asyncio

from api.deps import require_admin

router = APIRouter()

# logs.py vive en backend/api/ → subir 3 niveles llega a la raíz del proyecto
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_DIR = os.path.dirname(_BACKEND_DIR)
_MONITORING_JSON = os.path.join(_PROJECT_DIR, "monitoring.json")


def _load_config() -> dict:
    with open(_MONITORING_JSON, encoding="utf-8") as f:
        return json.load(f)


def _resolve_log_path(source: str) -> str:
    config = _load_config()
    sources = config.get("log_sources", {})
    if source not in sources:
        raise HTTPException(status_code=400, detail=f"Fuente desconocida: {source}")
    rel_path = sources[source]
    return os.path.join(_PROJECT_DIR, rel_path)


@router.get("/logs/latest", dependencies=[Depends(require_admin)])
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


@router.get("/logs/stream", dependencies=[Depends(require_admin)])
async def logs_stream(source: str = Query("backend")):
    path = _resolve_log_path(source)

    async def event_generator():
        # Si el archivo no existe aún, esperar a que aparezca
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
