"""Tests unitarios para interpolate() — el motor compartido de templates {{var}}."""
from .base import interpolate
from .state import FlowState, append_conversation_entry


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def test_resuelve_campos_meta():
    state = _state(contact_name="Ana")
    assert interpolate("{{contact_name}} escribió", state) == "Ana escribió"


def test_resuelve_claves_custom_de_data():
    state = _state()
    state.data["necesidad"] = "mesa para 4"
    assert interpolate("{{necesidad}}", state) == "mesa para 4"


def test_message_ya_no_es_placeholder():
    """{{message}} fue reemplazado por {{conversation}} — debe quedar literal."""
    state = _state()
    assert interpolate("hola {{message}}", state) == "hola {{message}}"


def test_placeholder_desconocido_queda_literal():
    state = _state()
    assert interpolate("hola {{no_existe}}", state) == "hola {{no_existe}}"


def test_ignora_valores_no_escalares_en_data():
    state = _state()
    state.data["lista"] = [1, 2, 3]
    assert interpolate("{{lista}}", state) == "{{lista}}"


def test_conversation_first_last_e_indices():
    state = _state()
    append_conversation_entry(state, "user", "quiero reservar")
    append_conversation_entry(state, "bot_reply", "¿para cuántos?")
    append_conversation_entry(state, "user", "para 4")

    assert interpolate("{{conversation.first}}", state) == "quiero reservar"
    assert interpolate("{{conversation.last}}", state) == "para 4"
    assert interpolate("{{conversation[0]}}", state) == "quiero reservar"
    assert interpolate("{{conversation[1]}}", state) == "¿para cuántos?"
    assert interpolate("{{conversation[-1]}}", state) == "para 4"


def test_conversation_origin():
    state = _state()
    append_conversation_entry(state, "user", "hola")
    append_conversation_entry(state, "bot_reply", "hola, ¿en qué te ayudo?")

    assert interpolate("{{conversation.first.origin}}", state) == "user"
    assert interpolate("{{conversation.last.origin}}", state) == "bot_reply"
    assert interpolate("{{conversation[1].content}}", state) == "hola, ¿en qué te ayudo?"


def test_conversation_transcripcion_completa():
    state = _state()
    append_conversation_entry(state, "user", "hola")
    append_conversation_entry(state, "bot_reply", "¿en qué te ayudo?")

    assert interpolate("{{conversation}}", state) == "Usuario: hola\nBot: ¿en qué te ayudo?"


def test_conversation_vacia():
    state = _state()
    assert interpolate("{{conversation}}", state) == ""


def test_conversation_indice_fuera_de_rango_queda_literal():
    state = _state()
    append_conversation_entry(state, "user", "hola")
    assert interpolate("{{conversation[5]}}", state) == "{{conversation[5]}}"


def test_append_conversation_entry_ignora_content_vacio():
    state = _state()
    append_conversation_entry(state, "user", "")
    append_conversation_entry(state, "user", None)
    assert "conversation" not in state.data
