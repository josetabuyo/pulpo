"""
Fixtures compartidos para tests de integración (tests/).
Apunta al servidor corriendo en BACKEND_PORT (mismo .env que el servidor).

La generación del reporte de tests (reports/test-report.json) vive en el
conftest.py de la raíz — cubre unitarios (pulpo/) e integración (tests/) en
un solo reporte, sin importar cuál de los dos (o ambos) se esté corriendo.
"""
import os
import pytest
import httpx
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PORT           = os.getenv("BACKEND_PORT", "8000")
BASE           = f"http://localhost:{PORT}"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN          = {"x-password": ADMIN_PASSWORD}


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE, timeout=5)
