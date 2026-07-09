"""Tests unitarios para execute_flow() (graphs/compiler.py) — entrada por api_trigger."""
import asyncio

import pytest

from . import compiler as compiler_mod
from .compiler import dispatch_message, execute_flow
from .nodes.state import FlowState

_FLOW = {
    "id": "flow1",
    "bot_id": "bot1",
    "definition": {
        "nodes": [{"id": "trigger1", "type": "api_trigger", "config": {}}],
        "edges": [],
    },
}


@pytest.mark.asyncio
async def test_api_trigger_arranca_conversacion():
    """execute_flow() con entry_node_id (api_trigger) siembra data['conversation']."""
    state = FlowState(message="hola desde webhook", contact_phone="user1")
    result = await execute_flow(_FLOW, state, entry_node_id="trigger1")
    assert result.data["conversation"] == [
        {"origin": "user", "content": "hola desde webhook", "type": "text"}
    ]


@pytest.mark.asyncio
async def test_api_trigger_sin_mensaje_no_crea_conversacion():
    state = FlowState(message="", contact_phone="user1")
    result = await execute_flow(_FLOW, state, entry_node_id="trigger1")
    assert "conversation" not in result.data


# ─── dispatch_message: conversación abierta más allá del wait_user ───────────

_BOT_ID = "__test_bot_dispatch__"
_CONN_ID = "__test_conn_dispatch__"
_CONTACT = "__test_contact_dispatch__"

_MESSAGE_FLOW_DEFINITION = {
    "nodes": [{
        "id": "trigger1", "type": "message_trigger",
        "config": {"connection_id": _CONN_ID},
    }],
    "edges": [],
}


def _patch_dispatch_env(monkeypatch):
    """dispatch_message resuelve bots/config/pausa vía imports locales — se
    parchea en los módulos de origen, no en compiler (import inline)."""
    import pulpo.core.config as config_mod
    import pulpo.core.paused as paused_mod

    monkeypatch.setattr(config_mod, "get_bots_for_connection",
                         lambda connection_id: [_BOT_ID] if connection_id == _CONN_ID else [])
    monkeypatch.setattr(config_mod, "load_config",
                         lambda: {"bots": [{"id": _BOT_ID, "name": "Test Bot"}]})
    monkeypatch.setattr(paused_mod, "is_paused", lambda bot_id: False)


@pytest.fixture
async def _dispatch_flow():
    from pulpo.core import db
    from pulpo.business import flows as flows_svc
    await db.init_db()
    flow = await flows_svc.create_flow(
        bot_id=_BOT_ID, name="Test dispatch flow",
        definition=_MESSAGE_FLOW_DEFINITION,
        connection_id=_CONN_ID, contact_phone=None, contact_filter=None,
    )
    try:
        yield flow
    finally:
        await db.delete_flow(flow["id"])
        await db.close_open_conversation(_BOT_ID, _CONTACT)


@pytest.mark.asyncio
async def test_dispatch_message_sin_conversacion_abierta_arranca_limpio(monkeypatch, _dispatch_flow):
    _patch_dispatch_env(monkeypatch)
    from pulpo.core import db
    await db.close_open_conversation(_BOT_ID, _CONTACT)

    state = FlowState(message="hola", contact_phone=_CONTACT, canal="telegram", connection_id=_CONN_ID)
    result = await dispatch_message(state, connection_id=_CONN_ID)

    assert result.data["_has_open_conv"] is False
    assert result.data["conversation"] == [{"origin": "user", "content": "hola", "type": "text"}]


_END_CONV_FLOW_DEFINITION = {
    "nodes": [
        {"id": "trigger1", "type": "message_trigger", "config": {"connection_id": _CONN_ID}},
        {"id": "end1", "type": "end_conversation", "config": {}},
    ],
    "edges": [{"source": "trigger1", "target": "end1"}],
}


@pytest.fixture
async def _end_conv_flow():
    from pulpo.core import db
    from pulpo.business import flows as flows_svc
    await db.init_db()
    flow = await flows_svc.create_flow(
        bot_id=_BOT_ID, name="Test end_conversation flow",
        definition=_END_CONV_FLOW_DEFINITION,
        connection_id=_CONN_ID, contact_phone=None, contact_filter=None,
    )
    try:
        yield flow
    finally:
        await db.delete_flow(flow["id"])
        await db.close_open_conversation(_BOT_ID, _CONTACT)


@pytest.mark.asyncio
async def test_dispatch_message_end_conversation_no_resucita_open_conversation(monkeypatch, _end_conv_flow):
    """Regresión: un flow que llega a end_conversation borra la fila — el
    guardado automático de fin de execute_flow() no debe volver a crearla
    solo porque state.data["conversation"] sigue poblado en memoria."""
    _patch_dispatch_env(monkeypatch)
    from pulpo.core import db
    await db.close_open_conversation(_BOT_ID, _CONTACT)

    state = FlowState(message="chau", contact_phone=_CONTACT, canal="telegram", connection_id=_CONN_ID)
    await dispatch_message(state, connection_id=_CONN_ID)

    assert await db.get_open_conversation(_BOT_ID, _CONTACT) is None


@pytest.mark.asyncio
async def test_dispatch_message_continua_conversacion_abierta_sin_wait_user(monkeypatch, _dispatch_flow):
    """Un segundo mensaje sin wait_user pendiente, pero con una fila en
    open_conversations (dejada por el turno anterior), restaura la historia
    y la encadena — no arranca una charla nueva."""
    _patch_dispatch_env(monkeypatch)
    import json as _json
    from pulpo.core import db

    await db.save_open_conversation(
        bot_id=_BOT_ID, contact_phone=_CONTACT, connection_id=_CONN_ID,
        flow_id=_dispatch_flow["id"],
        conversation_json=_json.dumps([
            {"origin": "user", "content": "busco un plomero", "type": "text"},
            {"origin": "bot_reply", "content": "¿en qué zona?"},
        ]),
    )

    state = FlowState(message="en Lugano", contact_phone=_CONTACT, canal="telegram", connection_id=_CONN_ID)
    result = await dispatch_message(state, connection_id=_CONN_ID)

    assert result.data["_has_open_conv"] is True
    assert result.data["conversation"] == [
        {"origin": "user", "content": "busco un plomero", "type": "text"},
        {"origin": "bot_reply", "content": "¿en qué zona?"},
        {"origin": "user", "content": "en Lugano", "type": "text"},
    ]


@pytest.mark.asyncio
async def test_dispatch_message_mensaje_concurrente_no_dispara_flow_paralelo(monkeypatch, _dispatch_flow):
    """
    Simula la ráfaga real: el mensaje 1 dispara execute_flow() y todavía no
    terminó (está "en vuelo") cuando llega el mensaje 2 del mismo contacto.
    El mensaje 2 NO debe llamar a execute_flow() en paralelo — se acumula y
    se despacha recién cuando el 1 libera el lock (encadenado, no paralelo).
    """
    _patch_dispatch_env(monkeypatch)
    from pulpo.core import db
    await db.close_open_conversation(_BOT_ID, _CONTACT)

    calls = []
    msg1_started = asyncio.Event()
    release_msg1 = asyncio.Event()
    real_execute_flow = compiler_mod.execute_flow

    async def _tracked_execute_flow(flow, state, entry_node_id=None):
        calls.append(state.message)
        if state.message == "hola":
            msg1_started.set()
            await release_msg1.wait()
        return await real_execute_flow(flow, state, entry_node_id=entry_node_id)

    monkeypatch.setattr(compiler_mod, "execute_flow", _tracked_execute_flow)

    state1 = FlowState(message="hola", contact_phone=_CONTACT, canal="telegram", connection_id=_CONN_ID)
    task1 = asyncio.create_task(dispatch_message(state1, connection_id=_CONN_ID))
    await asyncio.wait_for(msg1_started.wait(), timeout=2)

    # Mensaje 2 llega mientras el 1 sigue "corriendo" (bloqueado en execute_flow).
    state2 = FlowState(message="busco un plomero", contact_phone=_CONTACT, canal="telegram", connection_id=_CONN_ID)
    await dispatch_message(state2, connection_id=_CONN_ID)

    # No disparó un execute_flow paralelo — solo se acumuló.
    assert calls == ["hola"]
    assert compiler_mod._PENDING_MESSAGES.get((_BOT_ID, _CONTACT)) is not None

    release_msg1.set()
    await asyncio.wait_for(task1, timeout=2)

    # Recién ahora, encadenado (no paralelo), se procesó el mensaje 2.
    assert calls == ["hola", "busco un plomero"]
    assert compiler_mod._PENDING_MESSAGES.get((_BOT_ID, _CONTACT)) in (None, [])
    assert (_BOT_ID, _CONTACT) not in compiler_mod._IN_FLIGHT
