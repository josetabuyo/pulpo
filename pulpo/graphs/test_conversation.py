"""Tests unitarios para el dominio de conversación (graphs/conversation.py)."""
from .conversation import continue_conversation, record_bot_reply, start_conversation
from .nodes import MESSAGE_TRIGGER_TYPES, TRIGGER_TYPES
from .nodes.state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", contact_phone="user1")
    defaults.update(kwargs)
    return FlowState(**defaults)


def test_message_trigger_types_es_subconjunto_de_trigger_types():
    assert MESSAGE_TRIGGER_TYPES <= TRIGGER_TYPES


def test_api_trigger_no_es_conversacional():
    assert "api_trigger" in TRIGGER_TYPES
    assert "api_trigger" not in MESSAGE_TRIGGER_TYPES


def test_canales_de_mensajeria_son_conversacionales():
    assert {"message_trigger", "telegram_trigger", "whatsapp_trigger"} <= MESSAGE_TRIGGER_TYPES


def test_start_conversation_siembra_primer_turno():
    state = _state(message="quiero un plomero")
    start_conversation(state)
    assert state.data["conversation"] == [{"origin": "user", "content": "quiero un plomero"}]


def test_start_conversation_es_idempotente():
    """No debe duplicar el primer turno si el mismo mensaje matchea más de un flow."""
    state = _state(message="hola")
    start_conversation(state)
    start_conversation(state)
    assert len(state.data["conversation"]) == 1


def test_continue_conversation_agrega_turno_nuevo():
    state = _state(message="se me tapo la pileta")
    state.data["conversation"] = [
        {"origin": "user", "content": "necesito un plomero"},
        {"origin": "bot_reply", "content": "¿qué te pasó?"},
    ]
    continue_conversation(state)
    assert state.data["conversation"][-1] == {"origin": "user", "content": "se me tapo la pileta"}
    assert len(state.data["conversation"]) == 3


def test_record_bot_reply_requiere_conversacion_existente():
    state = _state()
    record_bot_reply(state, "hola, ¿en qué te ayudo?")
    assert "conversation" not in state.data


def test_record_bot_reply_agrega_turno_si_hay_conversacion():
    state = _state()
    start_conversation(state)
    record_bot_reply(state, "¿en qué te ayudo?")
    assert state.data["conversation"][-1] == {"origin": "bot_reply", "content": "¿en qué te ayudo?"}
