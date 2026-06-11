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

# Empresa de prueba que usan los tests de integración (empresa, flows, contacts).
TEST_BOT_ID  = "bot_test"
TEST_BOT_PWD = "bot_test"


def server_sim_mode() -> bool:
    """True si el server corriendo está en modo simulador (ENABLE_BOTS=false).
    Pregunta al server su modo real en vez de leer el env del proceso de tests."""
    try:
        r = httpx.get(f"{BASE}/api/mode", timeout=5)
        return r.json().get("mode") == "sim"
    except Exception:
        return False


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE, timeout=5)


# Cache de tokens JWT por (bot_id, password) — se reutiliza en toda la sesión de tests
_token_cache: dict[tuple, str] = {}


@pytest.fixture(scope="session")
def _base_client():
    """Cliente HTTP reutilizable para la sesión completa de tests."""
    return httpx.Client(base_url=BASE, timeout=5)


@pytest.fixture(scope="session", autouse=True)
def ensure_bot_test(_base_client):
    """
    Garantiza que exista la empresa de prueba `bot_test` (password `bot_test`).
    En worktrees dev suele existir de forma permanente; en producción se crea
    al inicio de la suite y se elimina al final (junto con sus flows).
    """
    created = False
    try:
        r = _base_client.get("/api/bots", headers=ADMIN)
        if r.status_code == 200 and not any(b["id"] == TEST_BOT_ID for b in r.json()):
            r = _base_client.post("/api/bots", headers=ADMIN, json={
                "id": TEST_BOT_ID, "name": "Bot Test", "password": TEST_BOT_PWD,
            })
            created = r.status_code == 201
    except httpx.HTTPError as e:
        # Server caído: los tests de integración fallarán solos con su propio contexto.
        print(f"[conftest] no se pudo verificar/crear {TEST_BOT_ID}: {e}")
    yield
    if created:
        try:
            flows = _base_client.get(f"/api/empresas/{TEST_BOT_ID}/flows", headers=ADMIN)
            if flows.status_code == 200:
                for f in flows.json():
                    _base_client.delete(f"/api/empresas/{TEST_BOT_ID}/flows/{f['id']}", headers=ADMIN)
            _base_client.delete(f"/api/bots/{TEST_BOT_ID}", headers=ADMIN)
        except httpx.HTTPError as e:
            print(f"[conftest] cleanup de {TEST_BOT_ID} falló: {e}")


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
