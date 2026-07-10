"""Tests unitarios para SendMessageNode."""
import pytest

from .reply import SendMessageNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


@pytest.mark.asyncio
async def test_reply_al_usuario_agrega_turno_bot_reply():
    node = SendMessageNode({"message": "¿en qué te ayudo?"})
    state = _state()
    state.data["conversation"] = [{"origin": "user", "content": "hola"}]
    state = await node.run(state)
    assert state.data["reply"] == "¿en qué te ayudo?"
    assert state.data["conversation"][-1] == {
        "origin": "bot_reply", "content": "¿en qué te ayudo?", "type": "text"
    }


@pytest.mark.asyncio
async def test_reply_sin_conversacion_previa_no_crea_una_huerfana():
    """record_bot_reply no debe iniciar una conversación por sí solo — solo
    la continúa. Si conversation nunca se creó (ej. start_conversation no
    corrió, o corrió con message vacío) no debe aparecer un data["conversation"]
    huérfano de un solo turno bot_reply."""
    node = SendMessageNode({"message": "ok"})
    state = await node.run(_state())
    assert state.data["reply"] == "ok"
    assert "conversation" not in state.data


@pytest.mark.asyncio
async def test_reply_interpola_conversation_last():
    node = SendMessageNode({"message": "dijiste: {{conversation.last}}"})
    state = _state()
    state.data["conversation"] = [{"origin": "user", "content": "hola"}]
    state = await node.run(state)
    assert state.data["reply"] == "dijiste: hola"
    assert state.data["conversation"][-1] == {
        "origin": "bot_reply", "content": "dijiste: hola", "type": "text"
    }


@pytest.mark.asyncio
async def test_envio_a_tercero_no_se_acumula_en_conversation():
    """Un send_message con `to` explícito (ej: notificar a un trabajador) no es un
    turno de la conversación con el usuario."""
    import os
    os.environ.pop("ENABLE_BOTS", None)
    node = SendMessageNode({"to": "12345", "message": "nuevo pedido"})
    state = await node.run(_state())
    assert "conversation" not in state.data


@pytest.mark.asyncio
async def test_sim_no_envia_telegram_real(monkeypatch, caplog):
    """En simulación (_sim=True), _send_telegram no debe intentar acceder a
    pulpo.core.state.clients — debe salir apenas loguea [sim], incluso con
    ENABLE_BOTS=true (namespaceado por-run, no por proceso)."""
    monkeypatch.setenv("ENABLE_BOTS", "true")
    node = SendMessageNode({"to": "12345", "message": "nuevo pedido", "channel": "telegram"})
    state = _state()
    state.data["_sim"] = True
    with caplog.at_level("INFO"):
        result = await node.run(state)
    assert "conversation" not in result.data
    assert any("[sim] TG" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_sim_no_envia_teli_real(monkeypatch, caplog):
    monkeypatch.setenv("ENABLE_BOTS", "true")
    node = SendMessageNode({"to": "12345", "message": "nuevo pedido", "channel": "teli"})
    state = _state()
    state.data["_sim"] = True
    with caplog.at_level("INFO"):
        await node.run(state)
    assert any("[sim] teli" in r.message for r in caplog.records)
