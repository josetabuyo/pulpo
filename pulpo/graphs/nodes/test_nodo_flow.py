"""Tests unitarios para NodoFlowNode."""
import pytest

from . import NODE_REGISTRY
from .nodo_flow import NodoFlowNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def test_nodo_flow_registrado_en_node_registry():
    assert NODE_REGISTRY["nodo_flow"] is NodoFlowNode


@pytest.mark.asyncio
async def test_nodo_flow_run_lanza_runtime_error():
    node = NodoFlowNode({"flow_id": "otro-flow", "params": {}, "output": "resultado"})
    with pytest.raises(RuntimeError):
        await node.run(_state())


def test_nodo_flow_config_schema_tiene_los_campos_esperados():
    schema = NodoFlowNode.config_schema()
    assert set(schema.keys()) == {"flow_id", "params", "output"}
    assert schema["flow_id"]["type"] == "select"
    assert schema["params"]["type"] == "dict"
    assert schema["output"]["type"] == "string"
