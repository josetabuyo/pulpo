"""Tests de integración: GateNode + BFS del compiler."""
import pytest
from ..compiler import _run_bfs
from .gate import _GATE_STORE, _GATE_WAITING_RUNS
from .state import FlowState


def _state(message: str = "hola", contact: str = "u1") -> FlowState:
    return FlowState(message=message, contact_phone=contact)


# ─── Flow: 2 triggers → gate → sentinel ────────────────────────────────────
#
#  node_a (trigger) ─┐
#                    ├→ node_gate (gate, sin config) → node_b (unknown type)
#  node_c (trigger) ─┘
#
# El gate recibe _in_degree=2 del compiler (2 flechas entrantes).
# node_b es de tipo desconocido — el BFS lo saltea pero lo encola si el gate permite.

_NODES = [
    {"id": "node_a",    "type": "api_trigger", "config": {}},
    {"id": "node_c",    "type": "api_trigger", "config": {}},
    {"id": "node_gate", "type": "gate",        "config": {}},
    {"id": "node_b",    "type": "_sentinel",   "config": {}},
]
_NODE_BY_ID = {n["id"]: n for n in _NODES}
# grafo manual (equivalente a _build_graph sobre los edges)
_GRAPH = {
    "node_a":    [("node_gate", None)],
    "node_c":    [("node_gate", None)],
    "node_gate": [("node_b",    None)],
}


@pytest.fixture(autouse=True)
def clear_store():
    _GATE_STORE.clear()
    _GATE_WAITING_RUNS.clear()
    yield
    _GATE_STORE.clear()
    _GATE_WAITING_RUNS.clear()


@pytest.mark.asyncio
async def test_bfs_stops_at_gate_first_message():
    """El BFS no encola node_b cuando el gate bloquea."""
    state = await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("primero"))
    assert "_has_waiting_gate" in state.data
    assert "gate_messages" not in state.data


@pytest.mark.asyncio
async def test_bfs_continues_after_gate_second_message():
    """El BFS encola node_b después de que el gate abre."""
    # Primera ejecución — gate bloquea
    s1 = await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("primero"))
    assert "_has_waiting_gate" in s1.data

    # Segunda ejecución — gate abre (nuevo BFS, nuevo visited set)
    s2 = await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("segundo"))
    assert "gate_messages" in s2.data
    assert s2.data["gate_messages"] == ["primero", "segundo"]
    # _has_waiting_gate NO debe estar porque el gate ya abrió
    assert "_has_waiting_gate" not in s2.data


@pytest.mark.asyncio
async def test_bfs_independent_contacts_gate():
    """Contactos distintos no comparten el estado del gate."""
    # user1 primer mensaje
    s1 = await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("a", contact="u1"))
    assert "_has_waiting_gate" in s1.data

    # user2 primer mensaje — gate de user2 está vacío, bloquea también
    s2 = await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("b", contact="u2"))
    assert "_has_waiting_gate" in s2.data

    # user1 segundo mensaje — abre solo para user1
    s1b = await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("c", contact="u1"))
    assert s1b.data.get("gate_messages") == ["a", "c"]

    # user2 sigue con su gate incompleto
    assert ("node_gate", "u2") in _GATE_STORE


# ─── Waiting run linkage ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bfs_stores_waiting_run_when_gate_blocks():
    """Cuando el gate bloquea con run_id, se almacena en _GATE_WAITING_RUNS."""
    await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("msg"), run_id="run-abc")
    assert _GATE_WAITING_RUNS.get(("node_gate", "u1")) == "run-abc"


@pytest.mark.asyncio
async def test_bfs_pops_waiting_run_when_gate_opens():
    """Cuando el gate abre en la segunda ejecución, _GATE_WAITING_RUNS se vacía."""
    # Primera ejecución bloquea y almacena run_id
    await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("primero"), run_id="run-1")
    assert ("node_gate", "u1") in _GATE_WAITING_RUNS

    # Segunda ejecución — gate abre, run-1 debe haber sido extraído del dict
    # (el engine intentaría cerrarlo en DB, pero sin DB no falla)
    await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("segundo"), run_id="run-2")
    assert ("node_gate", "u1") not in _GATE_WAITING_RUNS


@pytest.mark.asyncio
async def test_bfs_no_waiting_run_without_run_id():
    """Sin run_id, el gate no registra nada en _GATE_WAITING_RUNS."""
    await _run_bfs("node_a", _NODE_BY_ID, _GRAPH, _state("msg"))
    assert len(_GATE_WAITING_RUNS) == 0
