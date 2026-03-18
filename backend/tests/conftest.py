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

PORT = os.getenv("BACKEND_PORT", "8000")
BASE = f"http://localhost:{PORT}"
ADMIN = {"x-password": "admin"}
BAD   = {"x-password": "wrong"}


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE, timeout=5)
