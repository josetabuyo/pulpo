"""
Business logic for flow (agent graph) management.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

import logging
import os
import json
import uuid

import pulpo.core.db as db
from pulpo.core.config import load_config
from pulpo.graphs.node_types import NODE_TYPES
from pulpo.graphs.nodes import NODE_REGISTRY, TRIGGER_TYPES

logger = logging.getLogger(__name__)


def list_node_types() -> list[dict]:
    """
    Returns the catalog of node types: id, label, color, description, help, schema.
    Schema is an ordered list of field definitions for the frontend config panel.
    """
    result = []
    for nt in NODE_TYPES.values():
        node_class = NODE_REGISTRY.get(nt.id)
        schema_dict = node_class.config_schema() if node_class else {}
        schema = [{"key": k, **v} for k, v in schema_dict.items()]
        raw_doc = (node_class.__doc__ or "").strip() if node_class else ""
        help_text = raw_doc.split("\n\nConfig:")[0].strip() if raw_doc else ""
        result.append({
            "id":          nt.id,
            "label":       nt.label,
            "color":       nt.color,
            "description": nt.description,
            "help":        help_text,
            "schema":      schema,
        })
    return result


def list_google_accounts() -> list[dict]:
    """
    Returns Google service accounts configured via GOOGLE_SERVICE_ACCOUNT_JSON env var.
    Returns [{id, email, label}].
    """
    accounts = []
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        try:
            d = json.loads(sa_json)
            accounts.append({
                "id":    "default",
                "email": d.get("client_email", ""),
                "label": "Cuenta principal",
            })
        except ValueError:
            pass
    return accounts


def clear_sheet_cache() -> int:
    """
    Clears in-memory caches for fetch_sheet, search_sheet, and gsheet nodes.
    Returns the total number of entries cleared.
    """
    from pulpo.graphs.nodes.fetch_sheet import _sheet_cache
    from pulpo.graphs.nodes.search_sheet import _rows_cache as _search_cache
    from pulpo.graphs.nodes.gsheet import _rows_cache as _gsheet_cache
    n = len(_sheet_cache) + len(_search_cache) + len(_gsheet_cache)
    _sheet_cache.clear()
    _search_cache.clear()
    _gsheet_cache.clear()
    return n


async def list_flows(bot_id: str) -> list[dict]:
    """Returns all flows for a given bot. Raises KeyError if bot doesn't exist."""
    from pulpo.business.bots import get_bot
    if get_bot(bot_id) is None:
        raise KeyError(f"Bot '{bot_id}' no encontrado")
    return await db.get_flows(bot_id)


async def get_flow(flow_id: str, bot_id: str) -> dict | None:
    """
    Returns a flow dict if found and owned by bot_id, None otherwise.
    """
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        return None
    return flow


async def _validate_no_node_flow_cycles(definition: dict | None, flow_id: str | None) -> None:
    """
    Valida (dry-run, sin persistir nada) que un flow con nodos `nodo_flow` no
    forme un ciclo — ni consigo mismo ni con otros NodoFlow encadenados.
    Reusa `expand_node_flows` (misma lógica que corre el motor en runtime):
    si la expansión falla, el `ValueError` crudo se envuelve con contexto de
    negocio en vez de dejarlo propagar tal cual al caller.

    `flow_id`: id del flow que se está guardando (None si es un create nuevo
    — un flow sin id todavía no puede autoreferenciarse). Se agrega a
    `visiting` de arranque para detectar ciclos que vuelven a este flow.
    """
    definition = definition or {}
    nodes = definition.get("nodes", []) or []
    if not any(n.get("type") == "nodo_flow" for n in nodes):
        return

    from pulpo.graphs.compiler import expand_node_flows

    visiting = frozenset({flow_id}) if flow_id else frozenset()
    try:
        await expand_node_flows(nodes, definition.get("edges", []) or [], db.get_flow, visiting=visiting)
    except ValueError as e:
        raise ValueError(f"NodoFlow inválido: {e}") from e


async def create_flow(
    bot_id: str,
    name: str,
    definition: dict | None,
    connection_id: str | None,
    contact_phone: str | None,
    contact_filter: dict | None,
    flow_kind: str = "flow",
) -> dict:
    """
    Creates a new flow and returns the full flow dict.
    Raises ValueError on validation errors from the db layer, or if the
    definition contains a `nodo_flow` node that would form a cycle.
    """
    await _validate_no_node_flow_cycles(definition, flow_id=None)
    flow_id = await db.create_flow(
        bot_id=bot_id,
        name=name,
        definition=definition,
        connection_id=connection_id,
        contact_phone=contact_phone,
        contact_filter=contact_filter,
        flow_kind=flow_kind,
    )
    new_flow = await db.get_flow(flow_id)
    await db.create_flow_version(flow_id, name, new_flow.get("definition", {}))
    return new_flow


async def duplicate_flow(bot_id: str, flow_id: str, new_name: str) -> dict:
    """
    Duplica un flow existente bajo un nuevo nombre (misma definition,
    connection_id, contact_phone y contact_filter). El duplicado se crea
    INACTIVO — no debe responder en paralelo al original.

    Raises ValueError si el flow no existe o no pertenece a bot_id.
    """
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        raise ValueError("Flow no encontrado")

    new_flow = await create_flow(
        bot_id=bot_id,
        name=new_name,
        definition=flow.get("definition"),
        connection_id=flow.get("connection_id"),
        contact_phone=flow.get("contact_phone"),
        contact_filter=flow.get("contact_filter"),
        flow_kind=flow.get("flow_kind", "flow"),
    )
    return await update_flow(bot_id, new_flow["id"], {"active": False})


async def update_flow(bot_id: str, flow_id: str, updates: dict, save_version: bool = False) -> dict | None:
    """
    Updates a flow and returns the updated flow dict.
    Returns None if flow not found or not owned by bot_id.
    Also patches message_trigger node config when definition+connection_id or contact_filter change.

    If save_version and "definition" is part of the update, the flow's current
    (pre-update) definition is snapshotted into flow_versions first.
    """
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        return None

    # Inject connection_id and contact_filter into the message_trigger node config.
    if "definition" in updates:
        definition = updates["definition"]
        await _validate_no_node_flow_cycles(definition, flow_id=flow_id)
        new_conn = updates.get("connection_id")
        new_cf   = updates.get("contact_filter")
        for node in definition.get("nodes", []):
            if node.get("type") == "message_trigger":
                cfg = node.setdefault("config", {})
                if new_conn is not None:
                    cfg["connection_id"] = new_conn
                if new_cf is not None:
                    cfg["contact_filter"] = new_cf
                break

    if save_version and "definition" in updates:
        await db.create_flow_version(flow_id, flow["name"], flow["definition"])

    if updates:
        await db.update_flow(flow_id, **updates)
    return await db.get_flow(flow_id)


async def get_flow_versions(bot_id: str, flow_id: str) -> list[dict] | None:
    """Returns the saved version history (without definition) for a flow, or None if not owned."""
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        return None
    return await db.get_flow_versions(flow_id)


async def get_flow_version(bot_id: str, flow_id: str, version_id: int) -> dict | None:
    """Returns a single saved version (with full definition), or None if not found/not owned."""
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        return None
    version = await db.get_flow_version(version_id)
    if not version or version["flow_id"] != flow_id:
        return None
    return version


async def delete_flow(bot_id: str, flow_id: str) -> bool:
    """
    Deletes a flow.
    Returns True on success, False if flow not found or not owned by bot_id.
    """
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        return False
    await db.delete_flow(flow_id)
    return True


async def has_node_type(bot_id: str, node_type: str) -> bool:
    """Returns True if any flow in the bot contains a node of the given type."""
    return await db.bot_has_node_type(bot_id, node_type)


async def list_node_flows(bot_id: str) -> list[dict]:
    """
    Returns the bot's NodoFlows (flow_kind == "node_flow"), each with
    `inputs` parsed from its `definition` (empty list if it declares none) —
    used to populate the flow_id picker + dynamic params form in the editor —
    and `routes`, las salidas nombradas reales del sub-flow (calculadas con
    `compute_exit_routes` sobre su `nodes`/`edges`, misma lógica que usa el
    compilador para conectar el subgrafo) — la UI las usa para auto-completar
    `config.routes` del nodo `nodo_flow` que lo invoque (ver
    management/SPEC_NODOFLOW.md).
    """
    from pulpo.graphs.compiler import compute_exit_routes

    flows = await db.get_flows(bot_id)
    result = []
    for f in flows:
        if f.get("flow_kind") != "node_flow":
            continue
        full = await db.get_flow(f["id"])
        definition = (full or {}).get("definition", {}) or {}
        result.append({
            **f,
            "inputs": definition.get("inputs") or [],
            "routes": compute_exit_routes(definition.get("nodes") or [], definition.get("edges") or []),
        })
    return result


async def create_node_flow_from_selection(
    bot_id: str,
    source_flow_id: str,
    node_ids: list[str],
    name: str,
) -> dict:
    """
    Extrae los nodos de `source_flow_id` cuyo `id` está en `node_ids`, junto
    con los edges internos ENTRE esos nodos (descartando cualquier edge hacia/
    desde un nodo fuera de la selección), y crea un flow NUEVO
    `flow_kind="node_flow"`, `active=False`, con esa `definition`.

    El flow origen queda intacto — no se le borra ni modifica nada.
    Raises ValueError si `node_ids` está vacío, ninguno matchea, o el flow
    origen no existe / no pertenece a `bot_id`.
    """
    if not node_ids:
        raise ValueError("node_ids no puede estar vacío")

    source = await db.get_flow(source_flow_id)
    if not source or source["bot_id"] != bot_id:
        raise ValueError("Flow origen no encontrado")

    definition = source.get("definition", {}) or {}
    nodes = definition.get("nodes", []) or []
    edges = definition.get("edges", []) or []

    selected_ids = set(node_ids)
    selected_nodes = [n for n in nodes if n.get("id") in selected_ids]
    if not selected_nodes:
        raise ValueError("Ninguno de los node_ids coincide con nodos del flow origen")

    matched_ids = {n["id"] for n in selected_nodes}
    selected_edges = [
        e for e in edges
        if e.get("source") in matched_ids and e.get("target") in matched_ids
    ]

    new_flow = await create_flow(
        bot_id=bot_id,
        name=name,
        definition={"nodes": selected_nodes, "edges": selected_edges},
        connection_id=None,
        contact_phone=None,
        contact_filter=None,
        flow_kind="node_flow",
    )
    return await update_flow(bot_id, new_flow["id"], {"active": False})


async def replay_flow(bot_id: str, flow_id: str, from_date: str | None) -> dict:
    """
    Executes the flow against historical messages in the DB (from_delta_sync=True,
    so reply/llm nodes do not send real messages).
    Optionally filtered by from_date (YYYY-MM-DD).
    Returns {processed: int, skipped: int}.
    Raises ValueError if flow not found, not owned by bot, or missing trigger/connection_id.
    """
    flow = await db.get_flow(flow_id)
    if not flow or flow["bot_id"] != bot_id:
        raise ValueError("Flow no encontrado")

    nodes = flow.get("definition", {}).get("nodes", [])
    trigger = next(
        (n for n in nodes if n.get("type") in TRIGGER_TYPES),
        None,
    )
    if not trigger:
        raise ValueError("El flow no tiene un nodo trigger de mensajes")

    connection_id = trigger.get("config", {}).get("connection_id", "")
    if not connection_id:
        raise ValueError("El trigger no tiene connection_id configurado")

    trigger_cls = NODE_REGISTRY.get(trigger.get("type", ""))
    canal = getattr(trigger_cls, "channel", None) or "telegram"

    date_filter = ""
    date_params: dict = {}
    if from_date:
        date_filter = " AND timestamp >= :from_date"
        date_params["from_date"] = from_date

    from pulpo.core.db import AsyncSessionLocal, text as _text
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            _text(
                f"SELECT phone, name, body, timestamp FROM messages "
                f"WHERE connection_id = :cid AND outbound = 0{date_filter} "
                f"ORDER BY timestamp ASC"
            ),
            {"cid": connection_id, **date_params},
        )).fetchall()
        if not rows:
            rows = (await session.execute(
                _text(
                    f"SELECT phone, name, body, timestamp FROM messages "
                    f"WHERE connection_id = :eid AND outbound = 0{date_filter} "
                    f"ORDER BY timestamp ASC"
                ),
                {"eid": bot_id, **date_params},
            )).fetchall()

    if not rows:
        return {"processed": 0, "skipped": 0}

    from pulpo.graphs.compiler import execute_flow
    from pulpo.graphs.nodes.state import FlowState
    from datetime import datetime as _dt

    processed = 0
    skipped = 0

    for phone, name, body, ts_raw in rows:
        if not body or not body.strip():
            skipped += 1
            continue

        ts = None
        try:
            ts = _dt.fromisoformat(str(ts_raw))
        except (ValueError, TypeError):
            pass

        state = FlowState(
            message=body.strip(),
            message_type="text",
            connection_id=connection_id,
            canal=canal,
            bot_id=bot_id,
            contact_phone=phone,
            contact_name=name or phone,
            from_delta_sync=True,
            timestamp=ts,
        )
        await execute_flow(flow, state)
        processed += 1

    return {"processed": processed, "skipped": skipped}


async def trigger_flow(
    flow_id: str,
    node_id: str,
    message: str,
    contact_phone: str,
    contact_name: str,
) -> dict:
    """
    Triggers a flow from a specific api_trigger node.
    Raises ValueError if flow not found/inactive or node not found.
    Returns {ok: True, reply: str | None}.
    """
    flow = await db.get_flow(flow_id)
    if not flow or not flow.get("active"):
        raise ValueError("Flow no encontrado o inactivo")

    nodes = flow.get("definition", {}).get("nodes", [])
    trigger_node = next((n for n in nodes if n.get("id") == node_id), None)
    if not trigger_node or trigger_node.get("type") != "api_trigger":
        raise ValueError("Nodo api_trigger no encontrado")

    from pulpo.graphs.compiler import execute_flow
    from pulpo.graphs.nodes.state import FlowState

    state = FlowState(
        message=message,
        canal="api",
        contact_phone=contact_phone,
        contact_name=contact_name,
        bot_id=flow.get("bot_id", ""),
    )

    state = await execute_flow(flow, state, entry_node_id=node_id)
    return {"ok": True, "reply": state.data.get("reply")}


async def simulate_message(
    bot_id: str,
    message: str,
    sim_id: str | None = None,
    contact_name: str = "Simulación",
) -> dict:
    """
    Simula un mensaje entrante a una bot in-band (management/HANDOFF_SIMULACION_V2.md):
    equivalente a mandarle ese mensaje por Telegram, salvo que no sale de acá —
    mismo motor (execute_flow, resolve_flows) y misma resolución automática de
    flow/trigger que un mensaje real, sin que el caller tenga que indicar
    flow_id ni trigger_node_id (no hay nada que "aclarar": un mensaje real
    tampoco lo hace).

    Namespaceado por sim_id como contact_phone (nunca colisiona con un
    contacto real) y con state.data["_sim"]=True para que los nodos `guarded`
    salteen side-effects externos (envío real, persistencia de negocio,
    webhooks, escritura en Sheets). sim_id SIEMPRE se namespacea con prefijo
    "sim-" (se lo agregamos si el caller no lo puso).

    Soporta reanudación de wait_user: si ya hay un run parqueado para
    (bot_id, sim_id), el `message` nuevo continúa esa conversación.

    Recorre los flows activos de la bot (igual que dispatch_message) y corre
    el primero que tenga un trigger de mensajería (telegram/whatsapp/message);
    el primer reply no-None gana. Raises ValueError si la bot no tiene ningún
    flow activo con un trigger de ese tipo.
    Returns {ok: True, reply: str | None, run_id: str | None, sim_id: str}.
    """
    sim_id = sim_id or f"sim-{uuid.uuid4().hex[:8]}"
    if not sim_id.startswith("sim-"):
        sim_id = f"sim-{sim_id}"

    from pulpo.graphs.compiler import execute_flow, resume_wait_user_run, resolve_flows
    from pulpo.graphs.nodes import MESSAGE_TRIGGER_TYPES
    from pulpo.graphs.nodes.state import FlowState

    waiting = await db.get_waiting_gate_run(bot_id, sim_id)
    if waiting and waiting.get("resume_node_id"):
        resume_flow = await db.get_flow(waiting["flow_id"])
        if resume_flow:
            state = FlowState(
                message=message,
                canal="telegram",
                contact_phone=sim_id,
                contact_name=contact_name,
                bot_id=bot_id,
            )
            state.data["_sim"] = True
            state.data["_sim_id"] = sim_id
            state = await resume_wait_user_run(waiting, resume_flow, state)
            return {
                "ok": True,
                "reply": state.data.get("reply"),
                "run_id": state.data.get("_run_id"),
                "sim_id": sim_id,
            }

    # TODO(N-flows): con UN flow activo por bot (el caso de hoy) "el primero
    # que matchea" y "el flow que el caller quiere probar" son el mismo. El
    # día que un bot tenga 2+ flows activos con trigger de mensajería
    # simultáneos, esto deja de ser cierto — hay que aceptar un flow_id/
    # flow_name opcional en simulate_message() (y en el body de /simulate) y
    # filtrar acá por ese flow en vez de tomar el primero. Ver el TODO
    # espejado en tests/e2e/helpers.py.
    flows = await resolve_flows(bot_id)
    for flow in flows:
        nodes = flow.get("definition", {}).get("nodes", [])
        trigger_node = next(
            (n for n in nodes if n.get("type") in MESSAGE_TRIGGER_TYPES), None
        )
        if not trigger_node:
            continue

        trigger_cls = NODE_REGISTRY.get(trigger_node.get("type", ""))
        canal = getattr(trigger_cls, "channel", None) or "telegram"

        state = FlowState(
            message=message,
            canal=canal,
            contact_phone=sim_id,
            contact_name=contact_name,
            bot_id=bot_id,
        )
        state.data["_sim"] = True
        state.data["_sim_id"] = sim_id

        state = await execute_flow(flow, state, entry_node_id=trigger_node["id"])
        return {
            "ok": True,
            "reply": state.data.get("reply"),
            "run_id": state.data.get("_run_id"),
            "sim_id": sim_id,
        }

    raise ValueError("Esta bot no tiene ningún flow activo con un trigger de mensajería")


def seed_default_flows() -> None:
    """
    No-op. Flows require an explicit connection_id and cannot be seeded automatically.
    """
    pass


async def migrate_fetch_node_types() -> None:
    """
    Migración one-shot (idempotente): el viejo nodo genérico "fetch" (con
    config.source: "http"|"facebook") pasa a "fetch_http" — desde ADR-011,
    Facebook ya no es un source distinto, todo consumo de APIs externas
    (incluida Luganense) es un GET HTTP simple. Corre en cada startup; si no
    encuentra nodos "fetch" no hace nada.
    """
    flow_ids = await db.get_all_flow_ids()
    for flow_id in flow_ids:
        flow = await db.get_flow(flow_id)
        if not flow:
            continue
        definition = flow.get("definition") or {}
        nodes = definition.get("nodes", [])
        changed = False
        for node in nodes:
            if node.get("type") != "fetch":
                continue
            node.get("config", {}).pop("source", None)
            node["type"] = "fetch_http"
            changed = True
            logger.info(
                "[migrate_fetch_node_types] flow=%s node=%s: fetch → fetch_http",
                flow_id, node.get("id"),
            )
        if changed:
            await db.update_flow(flow_id, definition=definition)


async def list_bot_google_accounts(bot_id: str) -> list[dict]:
    """Returns Google accounts available to the bot (own + pulpo-default)."""
    conns = await db.get_google_connections(bot_id)
    return [{"id": c["id"], "email": c["email"], "label": c["label"]} for c in conns]
