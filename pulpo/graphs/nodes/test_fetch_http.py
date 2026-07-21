"""Tests unitarios para FetchHttpNode."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .fetch_http import FetchHttpNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def _fake_client(text: str, status_ok: bool = True, status_code: int = 200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
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
async def test_404_queda_registrado_en_fetch_errors():
    """Un 404 (u otro error HTTP) no debe quedar invisible — antes solo se logueaba
    y el output quedaba en None, indistinguible de "0 resultados reales"."""
    import httpx

    resp = MagicMock()
    resp.status_code = 404

    def _raise():
        raise httpx.HTTPStatusError("404", request=MagicMock(), response=resp)

    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(raise_for_status=_raise))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({"url": "https://api.test/buscar?q=x", "extract": "json"})
        state = await node.run(_state())

    assert state.data["context"] is None
    assert len(state.data["_fetch_errors"]) == 1
    assert state.data["_fetch_errors"][0]["status_code"] == 404
    assert state.data["_fetch_errors"][0]["url"] == "https://api.test/buscar?q=x"


@pytest.mark.asyncio
async def test_placeholder_sin_resolver_en_url_no_dispara_el_request():
    """Un `{{...}}` que sobrevivió a interpolate() (variable inexistente) es un
    bug de configuración del flow — no tiene sentido pedirle esa URL literal a
    un servidor, y el fallo de red resultante escondería la causa real."""
    client = MagicMock()
    client.get = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({"url": "https://api.test/buscar?q={{variable_inexistente}}", "extract": "json"})
        state = await node.run(_state())

    client.get.assert_not_awaited()
    assert state.data["context"] is None
    assert "placeholder" in state.data["_fetch_errors"][0]["error"]


@pytest.mark.asyncio
async def test_extract_fields_escribe_campos_planos_desde_json_anidado():
    client = _fake_client(json.dumps({
        "candidato": {
            "nombre": "Roberto Gómez",
            "contact_id": "6593910266",
            "contact_channel": "telegram",
            "descripcion": None,
        },
    }))
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/candidato?q=plomero",
            "extract": "json",
            "output": "servicios_luganense",
            "extract_fields": {
                "servicio": "candidato.nombre",
                "servicio_contact_id": "candidato.contact_id",
                "servicio_contact_channel": "candidato.contact_channel",
                "servicio_descripcion": "candidato.descripcion",
                "servicio_inexistente": "candidato.campo_que_no_existe",
            },
        })
        state = await node.run(_state())

    assert state.data["servicio"] == "Roberto Gómez"
    assert state.data["servicio_contact_id"] == "6593910266"
    assert state.data["servicio_contact_channel"] == "telegram"
    # null y ruta inexistente → la clave NO se escribe (no un "" que esconda el "no hay dato")
    assert "servicio_descripcion" not in state.data
    assert "servicio_inexistente" not in state.data
    # el output crudo se sigue guardando igual, sin romper prompts que ya lo usan
    assert "candidato" in state.data["servicios_luganense"]


@pytest.mark.asyncio
async def test_extract_fields_candidato_null_no_escribe_nada():
    client = _fake_client(json.dumps({"candidato": None}))
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/candidato?q=astrologo",
            "extract": "json",
            "output": "servicios_luganense",
            "extract_fields": {"servicio": "candidato.nombre"},
        })
        state = await node.run(_state())

    assert "servicio" not in state.data


@pytest.mark.asyncio
async def test_extract_fields_ignora_con_array_input():
    """extract_fields solo aplica al modo de un único GET — con array_input la
    respuesta es una LISTA, no hay un mapeo 1:1 inequívoco de a qué item aplicar."""
    client = _fake_client(json.dumps({"candidato": {"nombre": "Roberto Gómez"}}))
    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/candidato?q={{item.text}}",
            "extract": "json",
            "output": "resultados",
            "array_input": "queries",
            "extract_fields": {"servicio": "candidato.nombre"},
        })
        state = await node.run(_state(data={"queries": [{"text": "plomero"}]}))

    assert "servicio" not in state.data
    assert isinstance(state.data["resultados"], list)


@pytest.mark.asyncio
async def test_post_envia_body_json_interpolado():
    resp = MagicMock()
    resp.text = '{"ok": true, "id": 42}'
    resp.status_code = 201
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        node = FetchHttpNode({
            "url": "https://api.test/actividad-comercial",
            "method": "POST",
            "extract": "json",
            "output": "resultado_alta",
            "body": {
                "tipo": "pedido_servicio_concretado",
                "payload": {"profesional": "{{servicio}}", "direccion": "{{direccion}}"},
            },
        })
        state = _state(data={"servicio": "Ana Gómez", "direccion": "Calle Falsa 123"})
        state = await node.run(state)

    client.get.assert_not_called()
    _, kwargs = client.post.call_args
    assert kwargs["json"]["payload"]["profesional"] == "Ana Gómez"
    assert kwargs["json"]["payload"]["direccion"] == "Calle Falsa 123"
    assert kwargs["json"]["tipo"] == "pedido_servicio_concretado"
    assert "42" in state.data["resultado_alta"]


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
