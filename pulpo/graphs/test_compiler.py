"""Tests unitarios para execute_flow() (graphs/compiler.py) — entrada por api_trigger."""
import asyncio

import pytest

from . import compiler as compiler_mod
from .compiler import compute_exit_routes, dispatch_message, execute_flow, expand_node_flows
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


# ─── definition.variables: inyección en state.data (panel "VARIABLES DEL FLOW") ─

_FLOW_CON_VARIABLES = {
    "id": "flow-vars",
    "bot_id": "bot1",
    "definition": {
        "nodes": [{"id": "trigger1", "type": "api_trigger", "config": {}}],
        "edges": [],
        "variables": {"saludo": "Hola vecino!", "telefono_soporte": "011-5555-0000"},
    },
}


@pytest.mark.asyncio
async def test_execute_flow_inyecta_variables_del_flow_en_state():
    state = FlowState(message="hola", contact_phone="user1")
    result = await execute_flow(_FLOW_CON_VARIABLES, state, entry_node_id="trigger1")
    assert result.data["saludo"] == "Hola vecino!"
    assert result.data["telefono_soporte"] == "011-5555-0000"


@pytest.mark.asyncio
async def test_execute_flow_variables_no_pisan_state_ya_presente():
    """setdefault: si state.data ya trae la clave (ej. reanudando un wait_user
    con slots restaurados), la variable del flow NO debe pisar el valor real."""
    state = FlowState(message="hola", contact_phone="user1")
    state.data["saludo"] = "Ya viene con este valor de la conversación"
    result = await execute_flow(_FLOW_CON_VARIABLES, state, entry_node_id="trigger1")
    assert result.data["saludo"] == "Ya viene con este valor de la conversación"


@pytest.mark.asyncio
async def test_execute_flow_sin_variables_no_rompe():
    """Flows sin `variables` en la definition (la mayoría, hoy) siguen andando igual."""
    state = FlowState(message="hola", contact_phone="user1")
    result = await execute_flow(_FLOW, state, entry_node_id="trigger1")
    assert result.data["conversation"] == [
        {"origin": "user", "content": "hola", "type": "text"}
    ]


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
    """Nodo del medio es nodo_flow → sub-flow lineal con subflow_start/end
    explícitos. Verifica namespacing y que los edges conectan de punta a punta:
    la raíz es el `subflow_start` namespaceado y la salida el `subflow_end`."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "start", "type": "subflow_start", "config": {"key": "start"}},
                {"id": "a", "type": "llm", "config": {}},
                {"id": "b", "type": "send_message", "config": {}},
                {"id": "end", "type": "subflow_end", "config": {"route": ""}},
            ],
            "edges": [
                {"source": "start", "target": "a"},
                {"source": "a", "target": "b"},
                {"source": "b", "target": "end"},
            ],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}},
        {"id": "fin", "type": "send_message", "config": {}},
    ]
    edges = [
        {"source": "t", "target": "nf"},
        {"source": "nf", "target": "fin"},
    ]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    # El nodo_flow desaparece; aparecen los namespaceados (start/end incluidos).
    assert "nf" not in ids
    assert "sub1::a" not in ids  # (sanity: el prefijo es el id del nodo_flow, no del flow)
    assert "nf::start" in ids
    assert "nf::a" in ids
    assert "nf::b" in ids
    assert "nf::end" in ids
    # Sin params ni output → entry=subflow_start namespaceado, salida=subflow_end.
    adj = _adj(new_edges)
    assert "nf::a" in adj["nf::start"]    # edge interno start → a preservado
    assert "nf::b" in adj["nf::a"]        # edge interno preservado
    assert "nf::end" in adj["nf::b"]      # b → subflow_end
    assert "nf::start" in adj["t"]        # externo-in → subflow_start
    assert "fin" in adj["nf::end"]        # subflow_end → externo-out


@pytest.mark.asyncio
async def test_expand_con_params_inserta_set_state():
    """Cualquier clave del config del nodo_flow que no sea flow_id/output/routes
    es un parámetro (sin anidar en 'params') → se inserta un set_state
    sintético con config {field, value} por cada uno, encadenados, antes de
    la raíz. `output`, si está seteado, se reenvía también como parámetro
    'output' — sin ningún nodo sintético de copia posterior."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "inputs": [{"key": "ciudad", "label": "Ciudad", "type": "text", "default": ""}],
            "nodes": [
                {"id": "start", "type": "subflow_start", "config": {"key": "start"}},
                {"id": "a", "type": "llm", "config": {}},
                {"id": "end", "type": "subflow_end", "config": {"route": ""}},
            ],
            "edges": [
                {"source": "start", "target": "a"},
                {"source": "a", "target": "end"},
            ],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow",
         "config": {"flow_id": "sub1", "ciudad": "Lugano", "output": "destino"}},
    ]
    edges = [{"source": "t", "target": "nf"}, {"source": "nf", "target": "fin"}]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    pnode0 = ids["nf::__params__0"]
    pnode1 = ids["nf::__params__1"]
    assert pnode0["type"] == "set_state"
    assert pnode0["config"] == {"field": "ciudad", "value": "Lugano"}
    assert pnode1["type"] == "set_state"
    assert pnode1["config"] == {"field": "output", "value": "destino"}

    # externo-in → params0 → params1 → subflow_start
    adj = _adj(new_edges)
    assert "nf::__params__0" in adj["t"]
    assert "nf::__params__1" in adj["nf::__params__0"]
    assert "nf::start" in adj["nf::__params__1"]

    # sin nodo sintético de output — subflow_end conecta directo al externo-out
    assert "__output__" not in " ".join(ids.keys())
    assert "fin" in adj["nf::end"]


@pytest.mark.asyncio
async def test_expand_ciclo_lanza_valueerror():
    """Un flow_id que se referencia a sí mismo → ValueError."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "start", "type": "subflow_start", "config": {}},
                {"id": "self", "type": "nodo_flow", "config": {"flow_id": "sub1"}},
                {"id": "end", "type": "subflow_end", "config": {"route": ""}},
            ],
            "edges": [
                {"source": "start", "target": "self"},
                {"source": "self", "target": "end"},
            ],
        },
    }
    nodes = [{"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}}]
    edges = []

    with pytest.raises(ValueError, match="Ciclo"):
        await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))


@pytest.mark.asyncio
async def test_expand_anidado():
    """Un nodo_flow cuyo sub-flow contiene a su vez otro nodo_flow, cada uno con
    su propio subflow_start/subflow_end → ambos niveles se expanden y quedan
    conectados de punta a punta."""
    inner = {
        "id": "inner",
        "definition": {
            "nodes": [
                {"id": "istart", "type": "subflow_start", "config": {}},
                {"id": "x", "type": "llm", "config": {}},
                {"id": "iend", "type": "subflow_end", "config": {"route": ""}},
            ],
            "edges": [
                {"source": "istart", "target": "x"},
                {"source": "x", "target": "iend"},
            ],
        },
    }
    outer = {
        "id": "outer",
        "definition": {
            "nodes": [
                {"id": "ostart", "type": "subflow_start", "config": {}},
                {"id": "child", "type": "nodo_flow", "config": {"flow_id": "inner"}},
                {"id": "oend", "type": "subflow_end", "config": {"route": ""}},
            ],
            "edges": [
                {"source": "ostart", "target": "child"},
                {"source": "child", "target": "oend"},
            ],
        },
    }
    nodes = [
        {"id": "t", "type": "message_trigger", "config": {}},
        {"id": "nf", "type": "nodo_flow", "config": {"flow_id": "outer"}},
        {"id": "fin", "type": "send_message", "config": {}},
    ]
    edges = [
        {"source": "t", "target": "nf"},
        {"source": "nf", "target": "fin"},
    ]

    new_nodes, new_edges = await expand_node_flows(
        nodes, edges, _fetch_from({"outer": outer, "inner": inner})
    )
    ids = _by_id(new_nodes)
    # Ningún nodo_flow debe quedar sin expandir.
    assert all(n["type"] != "nodo_flow" for n in new_nodes)
    # Doble prefijo por el anidamiento; cada nivel conserva su start/end.
    assert "nf::ostart" in ids
    assert "nf::oend" in ids
    assert "nf::child::istart" in ids
    assert "nf::child::x" in ids
    assert "nf::child::iend" in ids

    # Conexión de punta a punta: externo-in → outer start → inner start → x →
    # inner end → outer end → externo-out.
    adj = _adj(new_edges)
    assert "nf::ostart" in adj["t"]
    assert "nf::child::istart" in adj["nf::ostart"]
    assert "nf::child::x" in adj["nf::child::istart"]
    assert "nf::child::iend" in adj["nf::child::x"]
    assert "nf::oend" in adj["nf::child::iend"]
    assert "fin" in adj["nf::oend"]


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
            {"id": "start", "type": "subflow_start", "config": {}},
            {"id": "s1", "type": "set_state",
             "config": {"field": "reply", "value": "sub-flow ejecutado"}},
            {"id": "end", "type": "subflow_end", "config": {"route": ""}},
        ],
        "edges": [
            {"source": "start", "target": "s1"},
            {"source": "s1", "target": "end"},
        ],
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
                 "config": {"flow_id": sub_flow["id"]}},
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

            # El sub-flow escribe directo en state.data (estado compartido,
            # no hay copia posterior) — visible en el padre sin config extra.
            assert result.data.get("reply") == "sub-flow ejecutado"
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


def _incoming_labeled(edges, target):
    """(source, label) de todos los edges que entran a `target`."""
    return {(e["source"], e.get("label") or None) for e in edges if e["target"] == target}


@pytest.mark.asyncio
async def test_expand_dos_subflow_end_por_route_conecta_por_label():
    """(caso d) Sub-flow con estructura tipo `get_data`: un condition rutea a un
    loop interno (`pedir_mas_info`) y a dos `subflow_end` (`found` / `not_found`).
    Cada salida externa del nodo_flow debe quedar conectada al target correcto
    por label, vía el subflow_end de esa ruta."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "start", "type": "subflow_start", "config": {}},
                {"id": "identificar", "type": "llm", "config": {}},
                {"id": "cond", "type": "condition", "config": {
                    "routes": ["found", "pedir_mas_info", "not_found"],
                }},
                {"id": "reask", "type": "llm", "config": {}},
                {"id": "end_found", "type": "subflow_end", "config": {"route": "found"}},
                {"id": "end_notfound", "type": "subflow_end", "config": {"route": "not_found"}},
            ],
            "edges": [
                {"source": "start", "target": "identificar"},
                {"source": "identificar", "target": "cond"},
                {"source": "cond", "target": "reask", "label": "pedir_mas_info"},
                {"source": "reask", "target": "identificar"},
                {"source": "cond", "target": "end_found", "label": "found"},
                {"source": "cond", "target": "end_notfound", "label": "not_found"},
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
        {"source": "nf", "target": "siguiente", "label": "found"},
        {"source": "nf", "target": "otro", "label": "not_found"},
    ]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    assert "nf" not in ids
    assert {"nf::start", "nf::cond", "nf::end_found", "nf::end_notfound"} <= set(ids)

    cond_out = _labels_from(new_edges, "nf::cond")
    # Loop interno intacto.
    assert cond_out.get("nf::reask") == "pedir_mas_info"
    # El condition rutea a cada subflow_end con su label.
    assert cond_out.get("nf::end_found") == "found"
    assert cond_out.get("nf::end_notfound") == "not_found"

    # Cada subflow_end reconecta a los targets externos preservando el label;
    # el matching por route en runtime hace que solo se siga el edge correcto.
    assert ("nf::end_found", "found") in _incoming_labeled(new_edges, "siguiente")
    assert ("nf::end_notfound", "not_found") in _incoming_labeled(new_edges, "otro")


@pytest.mark.asyncio
async def test_expand_output_se_reenvia_como_param_sin_nodo_de_copia():
    """(caso e) Con `output` configurado: se reenvía como parámetro `output`
    (para que el sub-flow lo use vía {{output}} si quiere) y las salidas
    (subflow_end) reconectan DIRECTO a los targets externos por label — sin
    ningún nodo sintético de copia posterior."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "start", "type": "subflow_start", "config": {}},
                {"id": "cond", "type": "condition", "config": {
                    "routes": ["found", "pedir_mas_info", "not_found"],
                }},
                {"id": "reask", "type": "llm", "config": {}},
                {"id": "end_found", "type": "subflow_end", "config": {"route": "found"}},
                {"id": "end_notfound", "type": "subflow_end", "config": {"route": "not_found"}},
            ],
            "edges": [
                {"source": "start", "target": "cond"},
                {"source": "cond", "target": "reask", "label": "pedir_mas_info"},
                {"source": "reask", "target": "cond"},
                {"source": "cond", "target": "end_found", "label": "found"},
                {"source": "cond", "target": "end_notfound", "label": "not_found"},
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
        {"source": "nf", "target": "siguiente", "label": "found"},
        {"source": "nf", "target": "otro", "label": "not_found"},
    ]

    new_nodes, new_edges = await expand_node_flows(nodes, edges, _fetch_from({"sub1": sub_flow}))

    ids = _by_id(new_nodes)
    # `output` se reenvía como parámetro (único, ya que "destino" no es una
    # clave real de config, es el valor del param) — sin nodo __output__.
    pnode = ids["nf::__params__0"]
    assert pnode["type"] == "set_state"
    assert pnode["config"] == {"field": "output", "value": "destino"}
    assert not any(nid.endswith("__output__") for nid in ids)

    # Cada subflow_end reconecta DIRECTO a los targets externos por label.
    out_found = _labels_from(new_edges, "nf::end_found")
    out_notfound = _labels_from(new_edges, "nf::end_notfound")
    assert out_found.get("siguiente") == "found"
    assert out_notfound.get("otro") == "not_found"


@pytest.mark.asyncio
async def test_expand_sin_subflow_start_error():
    """(caso a) Sub-flow sin ningún subflow_start → ValueError claro."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "a", "type": "llm", "config": {}},
                {"id": "end", "type": "subflow_end", "config": {"route": ""}},
            ],
            "edges": [{"source": "a", "target": "end"}],
        },
    }
    nodes = [{"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}}]
    with pytest.raises(ValueError, match="nodo de Inicio"):
        await expand_node_flows(nodes, [], _fetch_from({"sub1": sub_flow}))


@pytest.mark.asyncio
async def test_expand_dos_subflow_start_error():
    """(caso b) Sub-flow con dos subflow_start → ValueError (no soportado en v1)."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "s1", "type": "subflow_start", "config": {"key": "start"}},
                {"id": "s2", "type": "subflow_start", "config": {"key": "otra"}},
                {"id": "a", "type": "llm", "config": {}},
                {"id": "end", "type": "subflow_end", "config": {"route": ""}},
            ],
            "edges": [
                {"source": "s1", "target": "a"},
                {"source": "s2", "target": "a"},
                {"source": "a", "target": "end"},
            ],
        },
    }
    nodes = [{"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}}]
    with pytest.raises(ValueError, match="más de un nodo de Inicio"):
        await expand_node_flows(nodes, [], _fetch_from({"sub1": sub_flow}))


@pytest.mark.asyncio
async def test_expand_sin_subflow_end_error():
    """(caso c) Sub-flow sin ningún subflow_end → ValueError claro."""
    sub_flow = {
        "id": "sub1",
        "definition": {
            "nodes": [
                {"id": "start", "type": "subflow_start", "config": {}},
                {"id": "a", "type": "llm", "config": {}},
            ],
            "edges": [{"source": "start", "target": "a"}],
        },
    }
    nodes = [{"id": "nf", "type": "nodo_flow", "config": {"flow_id": "sub1"}}]
    with pytest.raises(ValueError, match="nodo de Fin"):
        await expand_node_flows(nodes, [], _fetch_from({"sub1": sub_flow}))


# ─── compute_exit_routes: rutas de salida nombradas de un sub-flow ───────────


def test_compute_exit_routes_una_salida_sin_route():
    """Un solo subflow_end con route vacío → sin rutas nombradas (una salida
    sin nombre no es una ruta seleccionable)."""
    nodes = [
        {"id": "start", "type": "subflow_start", "config": {}},
        {"id": "a", "type": "llm", "config": {}},
        {"id": "end", "type": "subflow_end", "config": {"route": ""}},
    ]
    assert compute_exit_routes(nodes) == []


def test_compute_exit_routes_dos_subflow_end_nombrados_caso_get_data():
    """Caso get_data: dos subflow_end con route 'found' / 'not_found' → esas dos
    son las salidas nombradas, en orden de aparición."""
    nodes = [
        {"id": "start", "type": "subflow_start", "config": {}},
        {"id": "cond", "type": "condition", "config": {
            "routes": ["found", "pedir_mas_info", "not_found"],
        }},
        {"id": "reask", "type": "llm", "config": {}},
        {"id": "end_found", "type": "subflow_end", "config": {"route": "found"}},
        {"id": "end_notfound", "type": "subflow_end", "config": {"route": "not_found"}},
    ]
    assert compute_exit_routes(nodes) == ["found", "not_found"]


def test_compute_exit_routes_ignora_route_vacio_entre_nombrados():
    """Un subflow_end sin route no aporta una ruta nombrada; los que sí tienen
    route se listan."""
    nodes = [
        {"id": "end_a", "type": "subflow_end", "config": {"route": "a"}},
        {"id": "end_vacio", "type": "subflow_end", "config": {"route": ""}},
        {"id": "end_b", "type": "subflow_end", "config": {"route": "b"}},
    ]
    assert compute_exit_routes(nodes) == ["a", "b"]


def test_compute_exit_routes_dedupe_conserva_orden():
    """Dos subflow_end con la misma route → dedupeada, conserva orden de primera
    aparición."""
    nodes = [
        {"id": "e1", "type": "subflow_end", "config": {"route": "a"}},
        {"id": "e2", "type": "subflow_end", "config": {"route": "b"}},
        {"id": "e3", "type": "subflow_end", "config": {"route": "a"}},
        {"id": "e4", "type": "subflow_end", "config": {"route": "c"}},
    ]
    assert compute_exit_routes(nodes) == ["a", "b", "c"]


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
