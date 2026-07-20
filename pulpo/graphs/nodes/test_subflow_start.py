"""Tests unitarios de SubflowStartNode — passthrough + registro."""
import pytest

from . import NODE_REGISTRY
from .subflow_start import SubflowStartNode
from .state import FlowState


def test_subflow_start_registrado():
    assert NODE_REGISTRY["subflow_start"] is SubflowStartNode


@pytest.mark.asyncio
async def test_subflow_start_es_passthrough():
    """run() devuelve el mismo state sin tocar state.data ni lanzar excepción."""
    state = FlowState(message="hola", contact_phone="user1")
    state.data["necesidad"] = "plomero"
    node = SubflowStartNode({"key": "start"})
    result = await node.run(state)
    assert result is state
    assert result.data == {"necesidad": "plomero"}


def test_subflow_start_config_schema_tiene_key():
    schema = SubflowStartNode.config_schema()
    assert schema["key"]["default"] == "start"
