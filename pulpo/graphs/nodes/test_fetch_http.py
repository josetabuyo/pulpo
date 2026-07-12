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
async def test_output_custom_no_pisa_context_de_otro_fetch():
    client = _fake_client('{"results": [{"nombre": "Plomero Juan"}]}')
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/buscar?q={message}",
            "extract": "json",
            "output": "resultado_servicio",
        })
        state = _state(data={"context": "algo previo que no debe pisarse"})
        state = await node.run(state)

    assert state.data["context"] == "algo previo que no debe pisarse"
    assert "Plomero Juan" in state.data["resultado_servicio"]


@pytest.mark.asyncio
async def test_output_custom_guarda_json_crudo_completo():
    client = _fake_client('{"results": [{"nombre": "Verdulería"}, {"nombre": "Otra"}], "total": 2}')
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/buscar?q={message}",
            "extract": "json",
            "output": "resultado_comercio",
        })
        state = await node.run(_state())

    assert "Verdulería" in state.data["resultado_comercio"]
    assert "Otra" in state.data["resultado_comercio"]
    assert "nombre" not in state.data


@pytest.mark.asyncio
async def test_array_input_hace_un_get_por_item_con_item_text():
    captured_urls = []

    async def fake_get(url):
        captured_urls.append(url)
        resp = MagicMock()
        resp.text = f'{{"echo": "{url}"}}'
        resp.raise_for_status = MagicMock()
        return resp

    client = MagicMock()
    client.get = fake_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/buscar?q={{item.text}}&tipo=servicios",
            "extract": "json",
            "output": "resultados_servicio",
            "array_input": "queries_servicio",
        })
        state = _state(data={"queries_servicio": [{"text": "plomero"}, {"text": "urgente"}]})
        state = await node.run(state)

    assert len(captured_urls) == 2
    assert "plomero" in captured_urls[0]
    assert "urgente" in captured_urls[1]
    assert isinstance(state.data["resultados_servicio"], list)
    assert len(state.data["resultados_servicio"]) == 2


@pytest.mark.asyncio
async def test_array_input_vacio_o_ausente_hace_un_solo_get():
    client = _fake_client('{"results": []}')
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/buscar?q={query}",
            "extract": "json",
            "array_input": "queries_servicio",
        })
        state = await node.run(_state())

    client.get.assert_awaited_once()
    assert isinstance(state.data["context"], str)


@pytest.mark.asyncio
async def test_array_input_item_fallido_no_frena_el_resto():
    call_count = {"n": 0}

    async def fake_get(url):
        call_count["n"] += 1
        if "malo" in url:
            raise RuntimeError("boom")
        resp = MagicMock()
        resp.text = '{"ok": true}'
        resp.raise_for_status = MagicMock()
        return resp

    client = MagicMock()
    client.get = fake_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/buscar?q={{item.text}}",
            "extract": "json",
            "output": "resultados",
            "array_input": "queries",
        })
        state = _state(data={"queries": [{"text": "malo"}, {"text": "bueno"}]})
        state = await node.run(state)

    assert call_count["n"] == 2
    assert state.data["resultados"][0] is None
    assert state.data["resultados"][1] == '{"ok": true}'
