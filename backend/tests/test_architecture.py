"""
Tests de GET /api/architecture (integración + unit de normalización).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import ADMIN, BAD


def test_architecture_requiere_auth(client):
    r = client.get("/api/architecture")
    assert r.status_code in (401, 422)
    r = client.get("/api/architecture", headers=BAD)
    assert r.status_code == 401


def test_architecture_shape(client):
    r = client.get("/api/architecture", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()

    assert body["system"]["name"] == "Pulpo"
    assert body["system"]["version_commit"]
    assert "contact_phone_semantics" in body["system"]

    fe = body["flow_engine"]
    assert sorted(fe["trigger_types"]) == ["message_trigger", "telegram_trigger", "whatsapp_trigger"]
    assert len(fe["nodes"]) >= 18
    triggers = [n for n in fe["nodes"] if n["is_trigger"]]
    assert len(triggers) == 3
    for n in fe["nodes"]:
        assert {"id", "label", "color", "description", "implemented", "is_trigger", "config_keys"} <= set(n)

    assert body["api"]["total_routes"] > 20
    assert any(r["path"] == "/api/architecture" for r in body["api"]["routes"])

    ch = body["channels"]
    assert isinstance(ch["telegram_bots"], int)
    assert isinstance(ch["wavi_sessions"], int)
    assert isinstance(ch["empresas"], int)
    assert ch["wa_poll_interval_seconds"] > 0

    # tests.* puede ser null (sin reporte) o un dict con el shape común
    for key in ("backend", "frontend"):
        rep = body["tests"][key]
        assert rep is None or {"total", "passed", "failed", "skipped", "tests"} <= set(rep)


def test_architecture_nodos_implementados_tienen_config_keys(client):
    r = client.get("/api/architecture", headers=ADMIN)
    nodes = r.json()["flow_engine"]["nodes"]
    summarize = next(n for n in nodes if n["id"] == "summarize")
    assert summarize["implemented"] is True
    trigger = next(n for n in nodes if n["id"] == "telegram_trigger")
    assert "connection_id" in trigger["config_keys"]
    assert "cooldown_hours" in trigger["config_keys"]


# ─── Unit: normalización del reporte Playwright ───────────────────────────────

def test_normalize_playwright_fixture():
    from api.architecture import _normalize_playwright
    raw = {
        "stats": {"startTime": "2026-06-11T20:00:00.000Z", "duration": 19500.0,
                  "expected": 41, "unexpected": 1, "skipped": 3, "flaky": 0},
        "suites": [{
            "title": "login.spec.cjs",
            "specs": [{
                "title": "login con admin navega al dashboard",
                "tests": [{"status": "expected", "results": [{"status": "passed", "duration": 800}]}],
            }],
            "suites": [],
        }],
    }
    norm = _normalize_playwright(raw)
    assert norm["total"] == 45
    assert norm["passed"] == 41
    assert norm["failed"] == 1
    assert norm["skipped"] == 3
    assert norm["duration"] == 19.5
    assert norm["tests"][0]["outcome"] == "passed"
    assert "login.spec.cjs" in norm["tests"][0]["nodeid"]


def test_normalize_playwright_vacio():
    from api.architecture import _normalize_playwright
    norm = _normalize_playwright({})
    assert norm["total"] == 0
    assert norm["tests"] == []
