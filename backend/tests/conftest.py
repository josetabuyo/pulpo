"""
Fixtures compartidos para todos los tests del backend.
Los tests corren contra el server en localhost:8001 (debe estar levantado).
"""
import pytest
import httpx

BASE = "http://localhost:8001"
ADMIN = {"x-password": "admin"}
BAD   = {"x-password": "wrong"}


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE, timeout=5)
