"""Tests unitarios para LLMNode."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from .llm import LLMNode
from .state import FlowState, append_conversation_entry


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def _mock_llm(content: str):
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content=content))
    return llm


@pytest.mark.asyncio
async def test_output_reply_convencion():
    node = LLMNode({"prompt": "system", "output": "reply"})
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("  hola mundo  ")):
        state = await node.run(_state())
    assert state.data["reply"] == "hola mundo"


@pytest.mark.asyncio
async def test_output_clave_custom_no_se_pierde():
    """Regresión del bug: output con nombre custom debe escribirse en state.data."""
    node = LLMNode({"prompt": "system", "output": "necesidad"})
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("reservar mesa")):
        state = await node.run(_state())
    assert state.data["necesidad"] == "reservar mesa"


@pytest.mark.asyncio
async def test_output_strip_uniforme():
    node = LLMNode({"prompt": "system", "output": "context"})
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("  con espacios  ")):
        state = await node.run(_state())
    assert state.data["context"] == "con espacios"


@pytest.mark.asyncio
async def test_from_delta_sync_no_llama_llm():
    node = LLMNode({"prompt": "system", "output": "reply"})
    with patch("pulpo.graphs.nodes.llm._build_llm") as mock_build:
        state = await node.run(_state(from_delta_sync=True))
    mock_build.assert_not_called()
    assert "reply" not in state.data


@pytest.mark.asyncio
async def test_sin_conversation_usa_state_message_como_fallback():
    """Compat: si no hay conversation acumulada, se manda solo state.message (como antes)."""
    node = LLMNode({"prompt": "system", "output": "reply"})
    llm = _mock_llm("ok")
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=llm):
        await node.run(_state(message="hola"))
    messages = llm.ainvoke.call_args.args[0]
    assert messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hola"},
    ]


@pytest.mark.asyncio
async def test_con_conversation_manda_historial_completo():
    node = LLMNode({"prompt": "system", "output": "reply"})
    state = _state()
    append_conversation_entry(state, "user", "hola")
    append_conversation_entry(state, "bot_reply", "¿en qué te ayudo?")
    append_conversation_entry(state, "user", "quiero reservar")

    llm = _mock_llm("ok")
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=llm):
        await node.run(state)

    messages = llm.ainvoke.call_args.args[0]
    assert messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¿en qué te ayudo?"},
        {"role": "user", "content": "quiero reservar"},
    ]


@pytest.mark.asyncio
async def test_error_en_llm_no_interrumpe_el_flow(caplog):
    node = LLMNode({"prompt": "system", "output": "reply"})
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(side_effect=Exception("timeout"))
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=llm):
        with caplog.at_level("ERROR"):
            state = await node.run(_state())
    assert "reply" not in state.data
    assert any("Error" in r.message for r in caplog.records)
