"""
Tests de autenticación del endpoint /api/wavi/qr-page.
"""
import pytest


@pytest.mark.integration
def test_qr_page_requires_auth(client):
    """GET /api/wavi/qr-page sin credenciales → 401."""
    r = client.get("/api/wavi/qr-page")
    assert r.status_code == 401


@pytest.mark.integration
def test_qr_page_with_auth_returns_html(client):
    """GET /api/wavi/qr-page con x-password → 200 con HTML (QR generado o mensaje de espera)."""
    from conftest import ADMIN
    r = client.get("/api/wavi/qr-page", headers=ADMIN)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
