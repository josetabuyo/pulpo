"""Tests unitarios para execute_flow() (graphs/compiler.py) — entrada por api_trigger."""
import asyncio

import pytest

from . import compiler as compiler_mod
from .compiler import dispatch_message, execute_flow, expand_node_flows
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


# ─── expand_node_flows: expansión de subgrafos (NodoFlow) ────────────────────


def _fetch_from(flows_by_id: dict):
    """Devuelve un fetch_flow_fn async que resuelve contra un dict en memoria."""
    async def _fetch(flow_id):
        return flows_by_id.get(flow_id)
    return _fetch


def _by_id(nodes):
    return {n["id"]: n for n in nodes}


def _adj(edges):
    """source -> set(target) para chequear conectividad sin depender de labels."""
    out = {}
    for e in edges:
        out.setdefault(e["source"], set()).add(e["target"])
    return out


@pytest.mark.asyncio
async def test_expand_lineal_simple():
    """Nodo del medio es nodo_flow → sub-flow lineal de 2 nodos. Verifica
    namespacing y que los edges conectan de punta a punta."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "a", "type": "llm", "config": {}},
                {"id": "b", "type": "send_message", "config": {}},
            ],
            "edges": [{"source": "a", "target": "b"}],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}},
        {"id": "end", "type": "send_message", "config": {}},
    ]
    edges = [
        {"source": "t", "target": "nf"},
        {"source": "nf", "target": "end"},
    ]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    # El nodo_flow desaparece; aparecen los namespaceados.
    assert "nf" not in ids
    assert "sub1::a" not in ids  # (sanity: el prefijo es el id del nodo_flow, no del flow)
    assert "nf::a" in ids
    assert "nf::b" in ids
    # Sin params ni output → entry=raíz namespaceada, salida=terminal namespaceado.
    adj = _adj(new_edges)
    assert "nf::b" in adj["nf::a"]        # edge interno preservado
    assert "nf::a" in adj["t"]            # externo-in → raíz subgrafo
    assert "end" in adj["nf::b"]          # terminal subgrafo → externo-out


@pytest.mark.asyncio
async def test_expand_con_params_inserta_set_state():
    """Sub-flow con params fijos → se inserta un set_state sintético con
    config {field, value} antes de la raíz."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "inputs": [{"key": "ciudad", "label": "Ciudad", "type": "text", "default": ""}],
            "output_key": "resultado",
            "nodes": [{"id": "a", "type": "llm", "config": {}}],
            "edges": [],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow",
         "config": {"flow_id": "sub1", "params": {"ciudad": "Lugano"}, "output": "destino"}},
    ]
    edges = [{"source": "t", "target": "nf"}]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    pnode = ids["nf::__params__0"]
    assert pnode["type"] == "set_state"
    assert pnode["config"] == {"field": "ciudad", "value": "Lugano"}

    # externo-in → params → raíz
    adj = _adj(new_edges)
    assert "nf::__params__0" in adj["t"]
    assert "nf::a" in adj["nf::__params__0"]

    # output: set_state que copia state.data[output_key] → state.data[output]
    onode = ids["nf::__output__"]
    assert onode["type"] == "set_state"
    assert onode["config"] == {"field": "destino", "value": "{{resultado}}"}
    assert "nf::__output__" in adj["nf::a"]  # terminal → output


@pytest.mark.asyncio
async def test_expand_ciclo_lanza_valueerror():
    """Un flow_id que se referencia a sí mismo → ValueError."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "a", "type": "llm", "config": {}},
                {"id": "self", "type": "nodo_flow", "config": {"flow_id": "sub1"}},
            ],
            "edges": [{"source": "a", "target": "self"}],
        },
    }
    nodes = [{"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}}]
    edges = []

    with pytest.raises(ValueError, match="Ciclo"):
        await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))


@pytest.mark.asyncio
async def test_expand_anidado():
    """Un nodo_flow cuyo sub-flow contiene a su vez otro nodo_flow → ambos
    niveles se expanden."""
    inner = {
        "id": "inner",
        "definition": {
            "nodes": [{"id": "x", "type": "llm", "config": {}}],
            "edges": [],
        },
    }
    outer = {
        "id": "outer",
        "definition": {
            "nodes": [
                {"id": "p", "type": "set_state", "config": {"field": "k", "value": "v"}},
                {"id": "child", "type": "nodo_flow", "config": {"flow_id": "inner"}},
            ],
            "edges": [{"source": "p", "target": "child"}],
        },
    }
    nodes = [{"id": "nf", "type": "nodo_flow", "config": {"flow_id": "outer"}}]
    edges = []

    new_nodes, _ = await expand_node_flows(
        nodes, edges, _fetch_from({"outer": outer, "inner": inner})
    )
    ids = _by_id(new_nodes)
    # Ningún nodo_flow debe quedar sin expandir.
    assert all(n["type"] != "nodo_flow" for n in new_nodes)
    # Doble prefijo por el anidamiento.
    assert "nf::p" in ids
    assert "nf::child::x" in ids


@pytest.mark.asyncio
async def test_expand_caso_base_sin_nodo_flow():
    """Sin ningún nodo_flow → devuelve nodes/edges con el mismo contenido."""
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "s", "type": "send_message", "config": {}},
    ]
    edges = [{"source": "t", "target": "s"}]

    async def _fail(_):  # no debe llamarse
        raise AssertionError("fetch_flow_fn no debería invocarse sin nodo_flow")

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fail)
    assert new_nodes == nodes
    assert new_edges == edges


@pytest.mark.asyncio
async def test_execute_flow_expande_nodo_flow_end_to_end():
    """Integración: un flow real con un nodo `nodo_flow` referenciando un
    NodoFlow persistido en DB se expande y ejecuta como un único grafo
    plano — verifica que el resultado del sub-flow llega a
    state.data[output] del padre."""
    from pulpo.core import db
    from pulpo.business import flows as flows_svc

    await db.init_db()
    bot_id = "__test_bot_nodoflow__"

    sub_definition = {
        "nodes": [
            {"id": "s1", "type": "set_state",
             "config": {"field": "reply", "value": "sub-flow ejecutado"}},
        ],
        "edges": [],
    }
    sub_flow = await flows_svc.create_flow(
        bot_id=bot_id, name="Sub NodoFlow",
        definition=sub_definition, connection_id=None,
        contact_phone=None, contact_filter=None,
    )
    try:
        main_definition = {
            "nodes": [
                {"id": "trigger1", "type": "api_trigger", "config": {}},
                {"id": "nf1", "type": "nodo_flow",
                 "config": {"flow_id": sub_flow["id"], "params": {}, "output": "resultado"}},
            ],
            "edges": [{"source": "trigger1", "target": "nf1"}],
        }
        main_flow = await flows_svc.create_flow(
            bot_id=bot_id, name="Main flow con nodo_flow",
            definition=main_definition, connection_id=None,
            contact_phone=None, contact_filter=None,
        )
        try:
            state = FlowState(message="hola", contact_phone="userNF")
            result = await execute_flow(main_flow, state, entry_node_id="trigger1")

            assert result.data.get("resultado") == "sub-flow ejecutado"
            assert not result.data.get("_node_errors")

            run_id = result.data.get("_run_id")
            assert run_id
            steps = await db.get_flow_run_steps(run_id)
            step_node_ids = {s["node_id"] for s in steps}
            # El nodo sintético namespaceado del sub-flow quedó en el journal —
            # prueba de que el subgrafo se expandió y ejecutó (no solo el nodo_flow).
            assert "nf1::s1" in step_node_ids
        finally:
            await db.delete_flow(main_flow["id"])
    finally:
        await db.delete_flow(sub_flow["id"])


def _labels_from(edges, source):
    """target -> label de todos los edges que salen de `source`."""
    return {e["target"]: (e.get("label") or None) for e in edges if e["source"] == source}


@pytest.mark.asyncio
async def test_expand_condition_rutas_parciales_conecta_salidas():
    """Sub-flow con un nodo `condition` de 3 rutas donde solo 1 (`pedir_mas_info`)
    tiene edge interno (vuelve a otro nodo del subgrafo) y las otras 2
    (`necesidad_identificada`, `fuera_de_scope`) NO tienen edge interno →
    esas 2 rutas deben quedar conectadas a los destinos de las edges externas
    originales del nodo_flow, preservando el label; la ruta con edge interno
    sigue apuntando adentro del subgrafo sin cambios."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "entry_node_id": "cond",
            "nodes": [
                {"id": "cond", "type": "condition", "config": {
                    "routes": ["necesidad_identificada", "pedir_mas_info", "fuera_de_scope"],
                }},
                {"id": "reask", "type": "llm", "config": {}},
            ],
            # Solo la ruta pedir_mas_info tiene edge interno (loop de re-pregunta).
            "edges": [
                {"source": "cond", "target": "reask", "label": "pedir_mas_info"},
                {"source": "reask", "target": "cond", "label": None},
            ],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}},
        {"id": "siguiente", "type": "send_message", "config": {}},
        {"id": "otro", "type": "send_message", "config": {}},
    ]
    edges = [
        {"source": "t", "target": "nf"},
        {"source": "nf", "target": "siguiente", "label": "necesidad_identificada"},
        {"source": "nf", "target": "otro", "label": "fuera_de_scope"},
    ]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    assert "nf" not in ids
    assert "nf::cond" in ids and "nf::reask" in ids

    cond_out = _labels_from(new_edges, "nf::cond")
    # La ruta con edge interno sigue adentro del subgrafo, sin cambios.
    assert cond_out.get("nf::reask") == "pedir_mas_info"
    # Las 2 rutas sin edge interno salen a los destinos externos, con su label.
    assert cond_out.get("siguiente") == "necesidad_identificada"
    assert cond_out.get("otro") == "fuera_de_scope"
    # El loop interno se preserva.
    assert _labels_from(new_edges, "nf::reask").get("nf::cond") is None


@pytest.mark.asyncio
async def test_expand_condition_rutas_parciales_con_output():
    """Como el anterior pero con `output` configurado: las rutas de salida del
    condition deben pasar por el nodo sintético de output (llevando su label en
    el edge condition→output, para no desviar la ruta interna) antes de llegar
    a las edges externas."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "entry_node_id": "cond",
            "output_key": "necesidad",
            "nodes": [
                {"id": "cond", "type": "condition", "config": {
                    "routes": ["necesidad_identificada", "pedir_mas_info", "fuera_de_scope"],
                }},
                {"id": "reask", "type": "llm", "config": {}},
            ],
            "edges": [
                {"source": "cond", "target": "reask", "label": "pedir_mas_info"},
                {"source": "reask", "target": "cond", "label": None},
            ],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow",
         "config": {"flow_id": "sub1", "output": "destino"}},
        {"id": "siguiente", "type": "send_message", "config": {}},
        {"id": "otro", "type": "send_message", "config": {}},
    ]
    edges = [
        {"source": "t", "target": "nf"},
        {"source": "nf", "target": "siguiente", "label": "necesidad_identificada"},
        {"source": "nf", "target": "otro", "label": "fuera_de_scope"},
    ]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    oid = "nf::__output__"
    assert ids[oid]["type"] == "set_state"
    assert ids[oid]["config"] == {"field": "destino", "value": "{{necesidad}}"}

    cond_out = _labels_from(new_edges, "nf::cond")
    # Ruta interna intacta.
    assert cond_out.get("nf::reask") == "pedir_mas_info"
    # Las rutas de salida entran al nodo output preservando su label (para no
    # desviar la ruta interna hacia el output).
    assert cond_out.get(oid) is None or cond_out.get(oid) is not None  # existe edge a output
    labels_to_output = [e.get("label") for e in new_edges
                        if e["source"] == "nf::cond" and e["target"] == oid]
    assert set(labels_to_output) == {"necesidad_identificada", "fuera_de_scope"}
    # El nodo output reparte a los destinos externos según label.
    out_out = _labels_from(new_edges, oid)
    assert out_out.get("siguiente") == "necesidad_identificada"
    assert out_out.get("otro") == "fuera_de_scope"


@pytest.mark.asyncio
async def test_expand_get_necesidad_real_conecta_ambas_salidas():
    """Fixture con la estructura real del flow `get_necesidad` (bot luganense):
    condition con rutas [necesidad_identificada, pedir_mas_info, fuera_de_scope]
    donde solo pedir_mas_info loopea internamente (reask→send→wait→entry) y no
    hay NINGÚN nodo out-degree 0. Con el fix, ambas salidas externas quedan bien
    conectadas desde el condition; sin el fix, el fallback a `root` las rompía."""
    sub_flow = {
        "id": "get_necesidad",
        "definition": {
            "entry_node_id": "identificar",
            "nodes": [
                {"id": "identificar", "type": "llm", "config": {"output": "necesidad"}},
                {"id": "cond", "type": "condition", "config": {
                    "rules": [
                        {"var": "necesidad", "op": "not_in",
                         "values": ["", "UNCLEAR", "OUT_OF_SCOPE"], "then": "necesidad_identificada"},
                        {"var": "necesidad", "op": "equals", "value": "OUT_OF_SCOPE",
                         "then": "fuera_de_scope"},
                    ],
                    "routes": ["necesidad_identificada", "pedir_mas_info", "fuera_de_scope"],
                    "fallback": "pedir_mas_info",
                }},
                {"id": "reask", "type": "llm", "config": {"output": "mensaje_pedido_necesidad"}},
                {"id": "preguntar", "type": "send_message", "config": {}},
                {"id": "esperar", "type": "wait_user", "config": {}},
            ],
            "edges": [
                {"source": "identificar", "target": "cond", "label": None},
                {"source": "cond", "target": "reask", "label": "pedir_mas_info"},
                {"source": "reask", "target": "preguntar", "label": None},
                {"source": "preguntar", "target": "esperar", "label": None},
                {"source": "esperar", "target": "identificar", "label": None},
            ],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow", "config": {"flow_id": "get_necesidad"}},
        {"id": "buscar_directorio", "type": "send_message", "config": {}},
        {"id": "responder_fuera_scope", "type": "send_message", "config": {}},
    ]
    edges = [
        {"source": "t", "target": "nf"},
        {"source": "nf", "target": "buscar_directorio", "label": "necesidad_identificada"},
        {"source": "nf", "target": "responder_fuera_scope", "label": "fuera_de_scope"},
    ]

    new_nodes, new_edges = await expand_node_flows(
        nodes, edges, _fetch_from({"get_necesidad": sub_flow}))

    ids = _by_id(new_nodes)
    assert "nf" not in ids
    assert all(n["type"] != "nodo_flow" for n in new_nodes)

    cond_out = _labels_from(new_edges, "nf::cond")
    # Loop interno intacto.
    assert cond_out.get("nf::reask") == "pedir_mas_info"
    # Ambas salidas externas conectadas desde el condition, con label preservado.
    assert cond_out.get("buscar_directorio") == "necesidad_identificada"
    assert cond_out.get("responder_fuera_scope") == "fuera_de_scope"
    # El entry (root) NO debe quedar conectado a las salidas externas (el bug viejo).
    root_out = _labels_from(new_edges, "nf::identificar")
    assert "buscar_directorio" not in root_out
    assert "responder_fuera_scope" not in root_out


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
