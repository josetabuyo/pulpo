"""Tests unitarios para interpolate() — el motor compartido de templates {{var}}."""
from .base import interpolate
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def test_resuelve_campos_meta():
    state = _state(message="quiero reservar", contact_name="Ana")
    assert interpolate("{{contact_name}} dijo: {{message}}", state) == "Ana dijo: quiero reservar"


def test_resuelve_claves_custom_de_data():
    state = _state()
    state.data["necesidad"] = "mesa para 4"
    assert interpolate("{{necesidad}}", state) == "mesa para 4"


def test_meta_tiene_prioridad_sobre_data():
    """Una clave de negocio en data no puede sombrear un campo meta del engine."""
    state = _state(message="mensaje real")
    state.data["message"] = "mensaje falso"
    assert interpolate("{{message}}", state) == "mensaje real"


def test_placeholder_desconocido_queda_literal():
    state = _state()
    assert interpolate("hola {{no_existe}}", state) == "hola {{no_existe}}"


def test_ignora_valores_no_escalares_en_data():
    state = _state()
    state.data["lista"] = [1, 2, 3]
    assert interpolate("{{lista}}", state) == "{{lista}}"
