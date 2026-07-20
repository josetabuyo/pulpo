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
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content=content, response_metadata={}))
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
async def test_output_interpola_placeholder():
    # Permite que un NodoFlow reciba, vía params, en qué clave de state.data
    # debe escribir su resultado (ej. reusar el mismo sub-flow para distintos
    # campos sin hardcodear el nombre de la clave dentro del sub-flow).
    node = LLMNode({"prompt": "system", "output": "{{output_field}}"})
    state = _state()
    state.data["output_field"] = "ubicacion"
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("Villa Lugano")):
        state = await node.run(state)
    assert state.data["ubicacion"] == "Villa Lugano"


@pytest.mark.asyncio
async def test_output_sin_placeholder_no_cambia_comportamiento():
    node = LLMNode({"prompt": "system", "output": "reply"})
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("hola")):
        state = await node.run(_state())
    assert state.data["reply"] == "hola"


@pytest.mark.asyncio
async def test_output_strip_uniforme():
    node = LLMNode({"prompt": "system", "output": "context"})
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm("  con espacios  ")):
        state = await node.run(_state())
    assert state.data["context"] == "con espacios"


@pytest.mark.asyncio
async def test_strip_think_block_de_modelo_de_razonamiento():
    """Regresión 2026-07-16: un modelo de razonamiento servido por el router
    (variantes DeepSeek R1) puede devolver el chain-of-thought crudo como
    `<think>...</think>` dentro de `content` en vez de separarlo — ese texto
    no debe filtrarse a state.data[output] (rompía la URL de un FetchHttpNode
    aguas abajo que interpolaba `{{rubro_elegido}}`)."""
    node = LLMNode({"prompt": "system", "output": "rubro_elegido"})
    content = "<think>\nAnalizo la necesidad...\nElijo Plomero.\n</think>\n\nPlomero"
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=_mock_llm(content)):
        state = await node.run(_state())
    assert state.data["rubro_elegido"] == "Plomero"


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


@pytest.mark.asyncio
async def test_contenido_vacio_reintenta_y_se_recupera():
    """Bug real 2026-07-13: la cascada cloud-first a veces devuelve contenido
    vacío sin levantar excepción — antes quedaba invisible, guardado tal cual
    como si fuera una decisión legítima del modelo. Un reintento resuelve el
    caso común (blip transitorio de un solo llamado)."""
    node = LLMNode({"prompt": "system", "output": "necesidad"})
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(side_effect=[
        SimpleNamespace(content="", response_metadata={}),
        SimpleNamespace(content="plomero urgencia canilla rota", response_metadata={}),
    ])
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=llm):
        state = await node.run(_state())

    assert state.data["necesidad"] == "plomero urgencia canilla rota"
    assert llm.ainvoke.await_count == 2
    assert "_llm_errors" not in state.data


@pytest.mark.asyncio
async def test_contenido_vacio_persistente_queda_registrado_en_llm_errors(caplog):
    """Si el contenido sigue vacío tras el reintento, no debe quedar invisible
    — se registra en state.data["_llm_errors"] (análogo a _fetch_errors de
    FetchHttpNode) para que los tests puedan validarlo contra el log."""
    node = LLMNode({"prompt": "system", "output": "necesidad"})
    llm = _mock_llm("")
    with patch("pulpo.graphs.nodes.llm._build_llm", return_value=llm):
        with caplog.at_level("ERROR"):
            state = await node.run(_state())

    assert state.data["necesidad"] == ""
    assert llm.ainvoke.await_count == 2  # 1 intento + 1 reintento
    assert len(state.data["_llm_errors"]) == 1
    assert state.data["_llm_errors"][0]["output"] == "necesidad"
    assert any("contenido vacío" in r.message for r in caplog.records)
