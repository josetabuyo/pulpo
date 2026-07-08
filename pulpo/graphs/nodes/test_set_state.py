"""Tests unitarios para SetStateNode."""
import pytest

from .set_state import SetStateNode
from .state import FlowState, append_conversation_entry


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


@pytest.mark.asyncio
async def test_set_valor_fijo_en_data():
    node = SetStateNode({"field": "direccion", "value": "calle falsa 123"})
    state = await node.run(_state())
    assert state.data["direccion"] == "calle falsa 123"


@pytest.mark.asyncio
async def test_set_con_template_de_meta_y_conversation():
    node = SetStateNode({"field": "resumen", "value": "{{contact_name}}: {{conversation.last}}"})
    state = _state(contact_name="Ana")
    append_conversation_entry(state, "user", "quiero reservar")
    state = await node.run(state)
    assert state.data["resumen"] == "Ana: quiero reservar"


@pytest.mark.asyncio
async def test_set_field_meta_usa_setattr():
    node = SetStateNode({"field": "contact_name", "value": "Nuevo Nombre"})
    state = await node.run(_state())
    assert state.contact_name == "Nuevo Nombre"
    assert "contact_name" not in state.data


@pytest.mark.asyncio
async def test_increment():
    node = SetStateNode({"field": "contador", "mode": "increment"})
    state = _state()
    state.data["contador"] = 2
    state = await node.run(state)
    assert state.data["contador"] == "3"


@pytest.mark.asyncio
async def test_sin_field_no_hace_nada():
    node = SetStateNode({"field": "", "value": "x"})
    state = await node.run(_state())
    assert state.data == {}
