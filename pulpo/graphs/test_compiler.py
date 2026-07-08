"""Tests unitarios para execute_flow() (graphs/compiler.py) — entrada por api_trigger."""
import pytest

from .compiler import execute_flow
from .nodes.state import FlowState

_FLOW = {
    "id": "flow1",
    "bot_id": "bot1",
    "definition": {
        "nodes": [{"id": "trigger1", "type": "api_trigger", "config": {}}],
        "edges": [],
    },
}


@pytest.mark.asyncio
async def test_api_trigger_arranca_conversacion():
    """execute_flow() con entry_node_id (api_trigger) siembra data['conversation']."""
    state = FlowState(message="hola desde webhook", contact_phone="user1")
    result = await execute_flow(_FLOW, state, entry_node_id="trigger1")
    assert result.data["conversation"] == [
        {"origin": "user", "content": "hola desde webhook", "type": "text"}
    ]


@pytest.mark.asyncio
async def test_api_trigger_sin_mensaje_no_crea_conversacion():
    state = FlowState(message="", contact_phone="user1")
    result = await execute_flow(_FLOW, state, entry_node_id="trigger1")
    assert "conversation" not in result.data
