"""
Fixtures compartidos para tests del paquete pulpo.
Apunta al servidor corriendo en BACKEND_PORT (mismo .env que el servidor).
Escribe monitor/test_report_backend.json al final de cada corrida.
"""
import json
import os
import time
import pytest
import httpx
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PORT           = os.getenv("BACKEND_PORT", "8000")
BASE           = f"http://localhost:{PORT}"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN          = {"x-password": ADMIN_PASSWORD}

_REPORT_PATH = Path(__file__).parent.parent / "monitor" / "test_report_backend.json"
_report_tests: list[dict] = []
_report_t0: float = 0.0


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE, timeout=5)


def pytest_sessionstart(session):
    global _report_t0
    _report_t0 = time.time()
    _report_tests.clear()


def pytest_runtest_logreport(report):
    if report.when == "call":
        outcome = report.outcome
    elif report.when == "setup" and report.outcome != "passed":
        outcome = "skipped" if report.skipped else "error"
    else:
        return
    _report_tests.append({
        "nodeid": report.nodeid,
        "outcome": outcome,
        "duration": round(report.duration, 3),
    })


def pytest_sessionfinish(session, exitstatus):
    counts: dict[str, int] = {}
    for t in _report_tests:
        counts[t["outcome"]] = counts.get(t["outcome"], 0) + 1
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "duration": round(time.time() - _report_t0, 2),
        "total": len(_report_tests),
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0) + counts.get("error", 0),
        "skipped": counts.get("skipped", 0),
        "exit_code": int(exitstatus),
        "tests": _report_tests,
    }
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _REPORT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _REPORT_PATH)
