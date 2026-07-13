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
async def test_max_tokens_se_pasa_a_build_llm():
    node = LLMNode({"prompt": "system", "max_tokens": 500})
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("hola")) as mock_build:
        await node.run(_state())
    assert mock_build.call_args.args[-1] == 500


@pytest.mark.asyncio
async def test_sin_max_tokens_pasa_none():
    node = LLMNode({"prompt": "system"})
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("hola")) as mock_build:
        await node.run(_state())
    assert mock_build.call_args.args[-1] is None


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
async def test_output_as_list_parte_por_lineas():
    node = LLMNode({"prompt": "system", "output": "queries_servicio", "output_as_list": True})
    respuesta = "plomero pérdida de agua\n\nplomero\npérdida de agua"
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm(respuesta)):
        state = await node.run(_state())
    assert state.data["queries_servicio"] == [
        {"text": "plomero pérdida de agua"},
        {"text": "plomero"},
        {"text": "pérdida de agua"},
    ]


@pytest.mark.asyncio
async def test_from_delta_sync_no_llama_llm():
    node = LLMNode({"prompt": "system", "output": "reply"})
    with patch("pulpo.graphs.nodes.llm._build_llm") as mock_build:
        state = await node.run(_state(from_delta_sync=True))
    mock_build.assert_not_called()
    assert "reply" not in state.data


@pytest.mark.asyncio
async def test_sin_conversation_usa_state_message():
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
async def test_con_conversation_no_duplica_el_historial_como_turnos():
    """El historial, si el prompt lo necesita, se pide explícito con {{conversation}}
    (interpolado en `system`) — no se manda además como turnos user/assistant separados."""
    node = LLMNode({"prompt": "Conversación:\n{{conversation}}", "output": "reply"})
    state = _state(message="quiero reservar")
    append_conversation_entry(state, "user", "hola")
    append_conversation_entry(state, "bot_reply", "¿en qué te ayudo?")
    append_conversation_entry(state, "user", "quiero reservar")

    llm = _mock_llm("ok")
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=llm):
        await node.run(state)

    messages = llm.ainvoke.call_args.args[0]
    assert messages == [
        {"role": "system", "content": "Conversación:\nUsuario: hola\nBot: ¿en qué te ayudo?\nUsuario: quiero reservar"},
        {"role": "user", "content": "quiero reservar"},
    ]


@pytest.mark.asyncio
async def test_context_no_se_agrega_si_el_prompt_no_lo_pide():
    """Ya no hay auto-append de {{context}} — si el prompt no lo menciona, no se manda."""
    node = LLMNode({"prompt": "system", "output": "reply"})
    state = _state()
    state.data["context"] = "info que no debería viajar"

    llm = _mock_llm("ok")
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=llm):
        await node.run(state)

    messages = llm.ainvoke.call_args.args[0]
    assert messages[0]["content"] == "system"


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
