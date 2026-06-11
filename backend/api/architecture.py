"""
GET /api/architecture — radiografía viva del sistema para la sección
Arquitectura del dashboard.

Todo sale de introspección (NODE_REGISTRY, NODE_TYPES, app.routes, config)
y de los reportes que escriben las suites de tests:
  monitor/test_report_backend.json   (hooks de pytest en tests/conftest.py)
  monitor/test_report_frontend.json  (reporter json de Playwright)

No expone secretos: ni tokens, ni teléfonos, ni nombres de contactos.
"""
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.routing import APIRoute

from api.deps import require_admin
from config import load_config, get_telegram_connections, get_wa_poll_interval
from graphs.node_types import NODE_TYPES
from graphs.nodes import NODE_REGISTRY, TRIGGER_TYPES

logger = logging.getLogger(__name__)

router = APIRouter()

_ROOT = Path(__file__).parent.parent.parent          # raíz del worktree
_MONITOR = _ROOT / "monitor"

_DESCRIPTION = (
    "Pulpo es un motor de workflows conversacionales (estilo n8n, casero): "
    "los mensajes entrantes de cada canal se normalizan a un FlowState y el engine "
    "ejecuta los flows activos de la empresa en BFS desde el trigger que aplica. "
    "Backend FastAPI + SQLite; frontend React + Vite; canales: Telegram (polling) "
    "y WhatsApp via wavi (poller sobre el CLI). Los flows se editan visualmente "
    "y se persisten como JSON (nodes + edges) en la base."
)


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_ROOT, capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "desconocido"
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("[architecture] git rev-parse falló: %s", e)
        return "desconocido"


def _load_json_or_none(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        logger.warning("[architecture] reporte corrupto %s: %s", path.name, e)
        return None


def _normalize_playwright(raw: dict) -> dict:
    """Aplana el JSON nativo de Playwright al shape común del reporte backend."""
    stats = raw.get("stats", {})
    tests: list[dict] = []

    def walk(suite: dict, prefix: str):
        title = suite.get("title", "")
        label = f"{prefix}{title}" if title else prefix
        for spec in suite.get("specs", []):
            for t in spec.get("tests", []):
                results = t.get("results", [])
                status = t.get("status") or (results[-1].get("status") if results else "unknown")
                outcome = {
                    "expected": "passed", "unexpected": "failed",
                    "skipped": "skipped", "flaky": "passed",
                }.get(status, status)
                duration_ms = sum(r.get("duration", 0) for r in results)
                tests.append({
                    "nodeid": f"{label} › {spec.get('title', '')}".strip(" ›"),
                    "outcome": outcome,
                    "duration": round(duration_ms / 1000, 2),
                })
        for child in suite.get("suites", []):
            walk(child, f"{label} › " if label else "")

    for s in raw.get("suites", []):
        walk(s, "")

    passed = stats.get("expected", 0) + stats.get("flaky", 0)
    failed = stats.get("unexpected", 0)
    skipped = stats.get("skipped", 0)
    return {
        "timestamp": stats.get("startTime"),
        "duration": round(stats.get("duration", 0) / 1000, 2),
        "total": passed + failed + skipped,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "tests": tests,
    }


def _flow_engine_nodes() -> list[dict]:
    nodes = []
    for type_id, nt in NODE_TYPES.items():
        cls = NODE_REGISTRY.get(type_id)
        config_keys: list[str] = []
        if cls is not None and hasattr(cls, "config_schema"):
            config_keys = list(cls.config_schema().keys())
        nodes.append({
            "id": type_id,
            "label": nt.label,
            "color": nt.color,
            "description": nt.description,
            "implemented": cls is not None,
            "is_trigger": type_id in TRIGGER_TYPES,
            "config_keys": config_keys,
        })
    return nodes


@router.get("/architecture", dependencies=[Depends(require_admin)])
async def get_architecture(request: Request) -> dict:
    config = load_config()

    routes = [
        {"path": r.path, "methods": sorted(m for m in r.methods if m != "HEAD"), "name": r.name}
        for r in request.app.routes
        if isinstance(r, APIRoute)
    ]

    backend_report = _load_json_or_none(_MONITOR / "test_report_backend.json")
    frontend_raw = _load_json_or_none(_MONITOR / "test_report_frontend.json")
    frontend_report = _normalize_playwright(frontend_raw) if frontend_raw else None

    import tools.wavi_driver as wd

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "system": {
            "name": "Pulpo",
            "version_commit": _git_commit(),
            "description": _DESCRIPTION,
            "contact_phone_semantics": {
                "telegram": "chat_id numérico",
                "wavi": "display name del contacto (check-updates no expone números)",
                "sim": "teléfono simulado",
            },
        },
        "flow_engine": {
            "trigger_types": sorted(TRIGGER_TYPES),
            "nodes": _flow_engine_nodes(),
        },
        "api": {
            "total_routes": len(routes),
            "routes": sorted(routes, key=lambda r: r["path"]),
        },
        "channels": {
            "telegram_bots": len(get_telegram_connections(config)),
            "wavi_sessions": len(wd.list_session_names()),
            "empresas": len(config.get("empresas", [])),
            "wa_poll_interval_seconds": get_wa_poll_interval(),
        },
        "tests": {
            "backend": backend_report,
            "frontend": frontend_report,
        },
    }
