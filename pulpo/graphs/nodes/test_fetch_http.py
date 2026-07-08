"""Tests unitarios para FetchHttpNode."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .fetch_http import FetchHttpNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def _fake_client(text: str, status_ok: bool = True):
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_config_schema_no_tiene_source():
    schema = FetchHttpNode.config_schema()
    assert "source" not in schema
    assert "url" in schema
    assert "extract" in schema


@pytest.mark.asyncio
async def test_sin_url_no_hace_request():
    node = FetchHttpNode({})
    state = await node.run(_state())
    assert state.data.get("context") is None


@pytest.mark.asyncio
async def test_reemplaza_query_con_necesidad_priorizada_sobre_mensaje():
    state = _state(message="mensaje crudo ruidoso", data={"necesidad": "zanahorias"})
    captured_url = {}

    async def fake_get(url):
        captured_url["url"] = url
        resp = MagicMock()
        resp.text = '{"results": []}'
        resp.raise_for_status = MagicMock()
        return resp

    client = MagicMock()
    client.get = fake_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({"url": "https://api.test/buscar?q={query}", "extract": "json"})
        await node.run(state)

    assert "zanahorias" in captured_url["url"]
    assert "mensaje crudo" not in captured_url["url"]


@pytest.mark.asyncio
async def test_extract_first_result_to_vars_vuelca_campos():
    client = _fake_client('{"results": [{"nombre": "Verdulería", "telefono": "123"}]}')
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/buscar?q={message}",
            "extract": "json",
            "extract_first_result_to_vars": True,
        })
        state = await node.run(_state())

    assert state.data["nombre"] == "Verdulería"
    assert state.data["telefono"] == "123"


@pytest.mark.asyncio
async def test_extract_first_result_to_vars_no_pisa_claves_reservadas():
    client = _fake_client('{"results": [{"route": "hackeado", "nombre": "ok"}]}')
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/buscar?q={message}",
            "extract": "json",
            "extract_first_result_to_vars": True,
        })
        state = _state()
        state.data["route"] = "original"
        state = await node.run(state)

    assert state.data["route"] == "original"
    assert state.data["nombre"] == "ok"
