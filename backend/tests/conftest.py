"""
Fixtures compartidos para todos los tests del backend.
El puerto se lee de BACKEND_PORT (mismo .env que usa el servidor),
así funciona sin cambios en cualquier worktree.
"""
import os
import pytest
import httpx
from dotenv import load_dotenv
from pathlib import Path

# Cargar el .env de la raíz del worktree (dos niveles arriba de tests/)
load_dotenv(Path(__file__).parent.parent.parent / ".env")

PORT           = os.getenv("BACKEND_PORT", "8000")
BASE           = f"http://localhost:{PORT}"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN          = {"x-password": ADMIN_PASSWORD}
BAD            = {"x-password": "wrong"}


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE, timeout=5)


# Cache de tokens JWT por (bot_id, password) — se reutiliza en toda la sesión de tests
_token_cache: dict[tuple, str] = {}


@pytest.fixture(scope="session")
def _base_client():
    """Cliente HTTP reutilizable para la sesión completa de tests."""
    return httpx.Client(base_url=BASE, timeout=5)


def get_empresa_token(bot_id: str, password: str, base_client) -> dict:
    """
    Obtiene (o reutiliza) un JWT Bearer token para una empresa.
    Compartido entre todos los tests para no agotar el rate limit de /api/empresa/login.
    """
    key = (bot_id, password)
    if key not in _token_cache:
        r = base_client.post("/api/empresa/login", json={"bot_id": bot_id, "password": password})
        assert r.status_code == 200, f"Login falló para {bot_id}: {r.text}"
        _token_cache[key] = r.json()["access_token"]
    return {"Authorization": f"Bearer {_token_cache[key]}"}
