"""Tests unitarios de SubflowEndNode — passthrough + registro."""
import pytest

from . import NODE_REGISTRY
from .subflow_end import SubflowEndNode
from .state import FlowState


def test_subflow_end_registrado():
    assert NODE_REGISTRY["subflow_end"] is SubflowEndNode


@pytest.mark.asyncio
async def test_subflow_end_es_passthrough():
    """run() devuelve el mismo state sin tocar state.data ni lanzar excepción."""
    state = FlowState(message="hola", contact_phone="user1")
    state.data["route"] = "found"
    node = SubflowEndNode({"route": "found"})
    result = await node.run(state)
    assert result is state
    assert result.data == {"route": "found"}


@pytest.mark.asyncio
async def test_subflow_end_route_vacia_es_passthrough():
    state = FlowState(message="hola", contact_phone="user1")
    node = SubflowEndNode({"route": ""})
    result = await node.run(state)
    assert result is state
    assert result.data == {}


def test_subflow_end_config_schema_tiene_route():
    schema = SubflowEndNode.config_schema()
    assert schema["route"]["default"] == ""
