"""Tests unitarios para ConditionNode."""
import pytest

from .condition import ConditionNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


@pytest.mark.asyncio
async def test_not_in_matchea_necesidad_concreta():
    node = ConditionNode({
        "rules": [
            {"var": "necesidad", "op": "not_in", "values": ["", "UNCLEAR", "OUT_OF_SCOPE"], "then": "necesidad_identificada"},
            {"var": "necesidad", "op": "equals", "value": "OUT_OF_SCOPE", "then": "fuera_de_scope"},
        ],
        "fallback": "pedir_mas_info",
    })
    state = await node.run(_state(data={"necesidad": "plomero pérdida de agua"}))
    assert state.data["route"] == "necesidad_identificada"


@pytest.mark.asyncio
async def test_equals_matchea_out_of_scope():
    node = ConditionNode({
        "rules": [
            {"var": "necesidad", "op": "not_in", "values": ["", "UNCLEAR", "OUT_OF_SCOPE"], "then": "necesidad_identificada"},
            {"var": "necesidad", "op": "equals", "value": "OUT_OF_SCOPE", "then": "fuera_de_scope"},
        ],
        "fallback": "pedir_mas_info",
    })
    state = await node.run(_state(data={"necesidad": "OUT_OF_SCOPE"}))
    assert state.data["route"] == "fuera_de_scope"


@pytest.mark.asyncio
async def test_ninguna_regla_matchea_usa_fallback():
    node = ConditionNode({
        "rules": [
            {"var": "necesidad", "op": "not_in", "values": ["", "UNCLEAR", "OUT_OF_SCOPE"], "then": "necesidad_identificada"},
            {"var": "necesidad", "op": "equals", "value": "OUT_OF_SCOPE", "then": "fuera_de_scope"},
        ],
        "fallback": "pedir_mas_info",
    })
    state = await node.run(_state(data={"necesidad": "UNCLEAR"}))
    assert state.data["route"] == "pedir_mas_info"


@pytest.mark.asyncio
async def test_var_ausente_se_trata_como_vacia():
    node = ConditionNode({
        "rules": [{"var": "necesidad", "op": "not_empty", "then": "necesidad_identificada"}],
        "fallback": "pedir_mas_info",
    })
    state = await node.run(_state(data={}))
    assert state.data["route"] == "pedir_mas_info"


@pytest.mark.asyncio
async def test_contains():
    node = ConditionNode({
        "rules": [{"var": "necesidad", "op": "contains", "value": "plomero", "then": "oficio"}],
        "fallback": "otro",
    })
    state = await node.run(_state(data={"necesidad": "necesito un plomero urgente"}))
    assert state.data["route"] == "oficio"


@pytest.mark.asyncio
async def test_primera_regla_que_matchea_gana():
    node = ConditionNode({
        "rules": [
            {"var": "necesidad", "op": "not_empty", "then": "primera"},
            {"var": "necesidad", "op": "equals", "value": "plomero", "then": "segunda"},
        ],
        "fallback": "fallback",
    })
    state = await node.run(_state(data={"necesidad": "plomero"}))
    assert state.data["route"] == "primera"


@pytest.mark.asyncio
async def test_sin_reglas_usa_fallback():
    node = ConditionNode({"rules": [], "fallback": "pedir_mas_info"})
    state = await node.run(_state(data={"necesidad": "plomero"}))
    assert state.data["route"] == "pedir_mas_info"


@pytest.mark.asyncio
async def test_max_visits_redirige_a_max_visits_route_tras_n_fallbacks_seguidos():
    """max_visits solo cuenta/aplica cuando el resultado de ESA visita queda en
    fallback (loop sin resolver) — tras N visitas seguidas sin resolver, la
    N-ésima se fuerza a max_visits_route."""
    node = ConditionNode({
        "rules": [{"var": "necesidad", "op": "not_empty", "then": "necesidad_identificada"}],
        "fallback": "pedir_mas_info",
        "max_visits": 2,
        "max_visits_route": "agotado",
        "_node_id": "n1",
    })
    state = await node.run(_state(data={}))  # necesidad vacía → fallback (visita 1/2)
    assert state.data["route"] == "pedir_mas_info"

    state = await node.run(state)  # sigue vacía → fallback (visita 2/2) → agotado
    assert state.data["route"] == "agotado"


@pytest.mark.asyncio
async def test_max_visits_no_pisa_un_acierto_en_la_ultima_visita():
    """Bug real corregido: si la N-ésima visita SÍ matchea una regla (no queda
    en fallback), max_visits no debe forzar max_visits_route — un acierto
    justo en el límite de reintentos tiene que ganar."""
    node = ConditionNode({
        "rules": [{"var": "necesidad", "op": "not_empty", "then": "necesidad_identificada"}],
        "fallback": "pedir_mas_info",
        "max_visits": 2,
        "max_visits_route": "agotado",
        "_node_id": "n1",
    })
    state = await node.run(_state(data={}))  # fallback (visita 1/2)
    assert state.data["route"] == "pedir_mas_info"

    state.data["necesidad"] = "plomero"
    state = await node.run(state)  # visita 2/2, pero matchea → no es fatiga
    assert state.data["route"] == "necesidad_identificada"


@pytest.mark.asyncio
async def test_sin_max_visits_route_no_cuenta_visitas():
    node = ConditionNode({
        "rules": [{"var": "necesidad", "op": "not_empty", "then": "necesidad_identificada"}],
        "fallback": "pedir_mas_info",
        "max_visits": 2,
        "_node_id": "n1",
    })
    state = await node.run(_state(data={"necesidad": "plomero"}))
    state = await node.run(state)
    assert state.data["route"] == "necesidad_identificada"
    assert "_visits_n1" not in state.data
