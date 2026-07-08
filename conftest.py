"""
Conftest raíz — genera reports/test-report.json al final de cualquier corrida
de pytest (unitarios en pulpo/, integración en tests/, o ambos juntos).

reports/ NO está en .gitignore a propósito: el reporte se commitea y pushea
junto con el código, así queda accesible desde la UI (sección de arquitectura)
sin depender de que alguien haya corrido los tests en esa misma máquina.
Cada corrida pisa el reporte anterior — es una foto del último resultado, no
un historial acumulado.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

_REPORT_PATH = Path(__file__).parent / "reports" / "test-report.json"
_report_tests: list[dict] = []
_report_t0: float = 0.0


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
    suite = "integration" if report.nodeid.startswith("tests/") else "unit"
    _report_tests.append({
        "nodeid": report.nodeid,
        "suite": suite,
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
