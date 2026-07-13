"""
Tests del módulo business/architecture.py y del endpoint /api/architecture.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── Unit tests (sin servidor) ──────────────────────────────────────────────────

def test_architecture_module_has_get_architecture():
    from pulpo.business.architecture import get_architecture
    import inspect
    assert inspect.iscoroutinefunction(get_architecture)


def test_architecture_get_architecture_shape(tmp_path):
    """get_architecture devuelve el shape esperado con monitor_dir/reports_dir vacíos."""
    from pulpo.business.architecture import get_architecture
    import asyncio

    monitor_dir = tmp_path / "monitor"
    monitor_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    root_dir = tmp_path

    fake_routes = [{"path": "/api/bots", "methods": ["GET"], "name": "get_bots"}]

    result = asyncio.run(get_architecture(
        routes=fake_routes,
        monitor_dir=monitor_dir,
        reports_dir=reports_dir,
        root_dir=root_dir,
    ))

    assert "generated_at" in result
    assert "system" in result
    assert result["system"]["name"] == "Pulpo"
    assert "flow_engine" in result
    assert "trigger_types" in result["flow_engine"]
    assert "nodes" in result["flow_engine"]
    assert "api" in result
    assert result["api"]["total_routes"] == 1
    assert "channels" in result
    assert "tests" in result
    assert result["tests"]["backend"] is None
    assert result["tests"]["frontend"] is None


def test_architecture_loads_test_report(tmp_path):
    """Si existe test-report.json en reports_dir lo incluye en la respuesta."""
    import json
    import asyncio
    from pulpo.business.architecture import get_architecture

    monitor_dir = tmp_path / "monitor"
    monitor_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    report = {
        "timestamp": "2026-06-29T12:00:00",
        "duration": 1.5,
        "total": 3,
        "passed": 3,
        "failed": 0,
        "skipped": 0,
        "tests": [],
    }
    (reports_dir / "test-report.json").write_text(json.dumps(report))

    result = asyncio.run(get_architecture(
        routes=[],
        monitor_dir=monitor_dir,
        reports_dir=reports_dir,
        root_dir=tmp_path,
    ))

    assert result["tests"]["backend"] is not None
    assert result["tests"]["backend"]["passed"] == 3


# ── Integration tests (requiere servidor en :8000) ────────────────────────────

@pytest.mark.integration
def test_architecture_endpoint_responds(client):
    """GET /api/architecture devuelve 200 con el shape correcto."""
    from conftest import ADMIN
    r = client.get("/api/architecture", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["system"]["name"] == "Pulpo"
    assert "flow_engine" in data
    assert "api" in data
    assert "channels" in data
