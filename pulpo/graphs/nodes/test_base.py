"""Tests unitarios para interpolate() — el motor compartido de templates {{var}}."""
import json

from .base import interpolate
from .state import FlowState, append_conversation_entry


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def test_resuelve_campos_meta():
    state = _state(contact_name="Ana")
    assert interpolate("{{contact_name}} escribió", state) == "Ana escribió"


def test_placeholder_anidado_dentro_de_un_valor_de_data_se_resuelve():
    # Caso NodoFlow: un prompt completo guardado como parámetro (state.data)
    # puede a su vez contener {{conversation}} u otros placeholders — deben
    # resolverse en la segunda pasada, no quedar literales.
    state = _state()
    append_conversation_entry(state, origin="user", content="hola")
    state.data["mi_prompt"] = "Contexto:\n{{conversation}}\n\nSaludá a {{contact_name}}."
    result = interpolate("{{mi_prompt}}", state)
    assert result == "Contexto:\nUsuario: hola\n\nSaludá a Juan."


def test_placeholder_anidado_no_reprocesa_mas_de_dos_pasadas():
    # Si el valor sustituido vuelve a contener el MISMO placeholder, no debe
    # recursar infinitamente — se corta a las 2 pasadas.
    state = _state()
    state.data["a"] = "{{a}}"
    assert interpolate("{{a}}", state) == "{{a}}"


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


def test_inserta_listas_como_json():
    state = _state()
    state.data["lista"] = [1, 2, 3]
    assert interpolate("{{lista}}", state) == "[\n  1,\n  2,\n  3\n]"


def test_inserta_dicts_como_json():
    state = _state()
    state.data["resultado"] = {"nombre": "Plomería Pérez", "zona": "Lugano"}
    assert interpolate("{{resultado}}", state) == json.dumps(
        {"nombre": "Plomería Pérez", "zona": "Lugano"}, ensure_ascii=False, indent=2
    )


def test_lista_vacia_se_inserta_como_json_vacio():
    state = _state()
    state.data["lista"] = []
    assert interpolate("{{lista}}", state) == "[]"


def test_valor_none_deja_placeholder_literal():
    """None no se resuelve como "" ni "{}" — queda {{key}} para detectar el fallo."""
    state = _state()
    state.data["resultado"] = None
    assert interpolate("{{resultado}}", state) == "{{resultado}}"


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
