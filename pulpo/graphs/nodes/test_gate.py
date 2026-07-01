"""Tests unitarios para GateNode."""
import pytest
from .gate import GateNode, _GATE_STORE
from .state import FlowState


def _state(message: str = "hola", contact: str = "user1") -> FlowState:
    return FlowState(message=message, contact_phone=contact)


def _gate(wait_for: int = 2, node_id: str = "gate_test") -> GateNode:
    return GateNode({"_in_degree": wait_for, "_node_id": node_id})


@pytest.fixture(autouse=True)
def clear_store():
    _GATE_STORE.clear()
    yield
    _GATE_STORE.clear()


@pytest.mark.asyncio
async def test_first_message_blocks():
    gate = _gate(wait_for=2)
    state = await gate.run(_state("mensaje 1"))
    assert state.data.get("_gate_blocked") is True
    assert "gate_messages" not in state.data


@pytest.mark.asyncio
async def test_second_message_opens():
    gate = _gate(wait_for=2)
    state = await gate.run(_state("mensaje 1"))
    assert state.data.pop("_gate_blocked")

    state2 = await gate.run(_state("mensaje 2"))
    assert "_gate_blocked" not in state2.data
    assert state2.data["gate_messages"] == ["mensaje 1", "mensaje 2"]


@pytest.mark.asyncio
async def test_store_cleared_after_open():
    gate = _gate(wait_for=2, node_id="gate_clear")
    key = ("gate_clear", "user1")
    await gate.run(_state("a"))
    await gate.run(_state("b"))
    assert key not in _GATE_STORE


@pytest.mark.asyncio
async def test_independent_contacts():
    gate = _gate(wait_for=2, node_id="gate_contacts")
    # user1 primer mensaje
    s1 = await gate.run(_state("hola", contact="user1"))
    assert s1.data.get("_gate_blocked") is True

    # user2 primer mensaje — no debe abrir el gate de user1
    s2 = await gate.run(_state("hi", contact="user2"))
    assert s2.data.get("_gate_blocked") is True

    # user1 segundo mensaje — abre solo para user1
    s1b = await gate.run(_state("mundo", contact="user1"))
    assert "_gate_blocked" not in s1b.data
    assert s1b.data["gate_messages"] == ["hola", "mundo"]

    # user2 sigue bloqueado
    assert ("gate_contacts", "user2") in _GATE_STORE


@pytest.mark.asyncio
async def test_wait_for_3():
    gate = _gate(wait_for=3)
    s1 = await gate.run(_state("uno"))
    s2 = await gate.run(_state("dos"))
    assert s1.data.get("_gate_blocked") is True
    assert s2.data.get("_gate_blocked") is True

    s3 = await gate.run(_state("tres"))
    assert "_gate_blocked" not in s3.data
    assert s3.data["gate_messages"] == ["uno", "dos", "tres"]


@pytest.mark.asyncio
async def test_gate_resets_after_open():
    """Después de abrirse, el gate acepta un nuevo ciclo."""
    gate = _gate(wait_for=2)
    await gate.run(_state("a"))
    await gate.run(_state("b"))  # abre

    s1 = await gate.run(_state("c"))
    assert s1.data.get("_gate_blocked") is True
    s2 = await gate.run(_state("d"))
    assert s2.data["gate_messages"] == ["c", "d"]
