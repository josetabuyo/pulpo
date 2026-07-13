"""Tests unitarios para RouterNode."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .router import RouterNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def _fake_llm(response_text: str):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=response_text))
    return llm


@pytest.mark.asyncio
async def test_router_no_manda_variables_de_mas_por_default():
    node = RouterNode({
        "prompt": "clasificá",
        "routes": ["necesidad_identificada", "pedir_mas_info"],
        "fallback": "pedir_mas_info",
    })
    with patch("pulpo.graphs.nodes.router._build_llm", return_value=_fake_llm("necesidad_identificada")) as mock_build_llm:
        state = await node.run(_state(message="necesito un plomero", data={"necesidad": "plomero", "_visits_router": 2}))

    llm = mock_build_llm.return_value
    messages = llm.ainvoke.call_args[0][0]
    user_message = messages[1]["content"]

    assert user_message == "Mensaje: necesito un plomero"
    assert "plomero" not in user_message.replace("necesito un plomero", "")
    assert "_visits_router" not in user_message
    assert state.data["route"] == "necesidad_identificada"


@pytest.mark.asyncio
async def test_router_setea_route_valida():
    node = RouterNode({
        "prompt": "clasificá",
        "routes": ["necesidad_identificada", "pedir_mas_info", "fuera_de_scope"],
        "fallback": "pedir_mas_info",
    })
    with patch("pulpo.graphs.nodes.router._build_llm", return_value=_fake_llm("necesidad_identificada")):
        state = await node.run(_state(data={"necesidad": "plomero"}))

    assert state.data["route"] == "necesidad_identificada"


@pytest.mark.asyncio
async def test_router_usa_fallback_si_respuesta_invalida():
    node = RouterNode({
        "prompt": "clasificá",
        "routes": ["necesidad_identificada", "pedir_mas_info"],
        "fallback": "pedir_mas_info",
    })
    with patch("pulpo.graphs.nodes.router._build_llm", return_value=_fake_llm("algo_no_valido")):
        state = await node.run(_state())

    assert state.data["route"] == "pedir_mas_info"


@pytest.mark.asyncio
async def test_router_contenido_vacio_reintenta_y_se_recupera():
    """Bug real 2026-07-13: la cascada cloud-first a veces devuelve contenido
    vacío sin levantar excepción — antes eso nunca matchea `routes` y cae al
    fallback en silencio, indistinguible de una clasificación genuina hacia
    esa rama (ej. "noticias" como fallback, pero el vecino pedía un producto).
    Un reintento resuelve el caso común (blip transitorio de un solo llamado)."""
    node = RouterNode({
        "prompt": "clasificá",
        "routes": ["comercio", "producto", "servicio", "noticias"],
        "fallback": "noticias",
    })
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[MagicMock(content=""), MagicMock(content="producto")])
    with patch("pulpo.graphs.nodes.router._build_llm", return_value=llm):
        state = await node.run(_state(message="necesito comprar focos LED"))

    assert state.data["route"] == "producto"
    assert llm.ainvoke.await_count == 2
    assert "_llm_errors" not in state.data


@pytest.mark.asyncio
async def test_router_contenido_vacio_persistente_cae_a_fallback_y_queda_registrado():
    node = RouterNode({
        "prompt": "clasificá",
        "routes": ["comercio", "producto", "servicio", "noticias"],
        "fallback": "noticias",
    })
    with patch("pulpo.graphs.nodes.router._build_llm", return_value=_fake_llm("")):
        state = await node.run(_state())

    assert state.data["route"] == "noticias"
    assert len(state.data["_llm_errors"]) == 1
    assert state.data["_llm_errors"][0]["output"] == "route"


@pytest.mark.asyncio
async def test_router_max_visits_redirige_sin_llamar_llm_de_nuevo():
    node = RouterNode({
        "prompt": "clasificá",
        "routes": ["necesidad_identificada", "pedir_mas_info"],
        "fallback": "pedir_mas_info",
        "max_visits": 2,
        "max_visits_route": "necesidad_identificada",
        "_node_id": "n1",
    })
    with patch("pulpo.graphs.nodes.router._build_llm", return_value=_fake_llm("pedir_mas_info")) as mock_build_llm:
        state = await node.run(_state(data={}))
        state = await node.run(state)

    assert state.data["route"] == "necesidad_identificada"
    mock_build_llm.assert_called_once()
