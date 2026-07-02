"""
Flow Engine — el motor que ejecuta flows.

Responsabilidades:
  - resolve_flows(): encuentra los flows activos de una bot
  - execute_flow(): corre los nodos de un flow en BFS desde su trigger
  - run_flows(): orquesta ambos y devuelve el FlowState con reply

Colaboradores:
  - trigger_match.select_trigger(): decide si un trigger aplica al mensaje
  - cooldown.flow_cooldown: rate limit de replies por (flow, contacto)

Los adapters (Telegram, Wavi, Sim) normalizan el mensaje a FlowState
y llaman a run_flows(). El engine no sabe nada de protocolos.
"""
import copy
import json
import logging
import os
import uuid
from datetime import datetime

from .cooldown import cooldown_hours, flow_cooldown
from .nodes import NODE_REGISTRY, TRIGGER_TYPES
from .nodes.state import FlowState
from .trigger_match import select_trigger

logger = logging.getLogger(__name__)


def _serialize_state(state: FlowState) -> str:
    return json.dumps({
        "message": state.message,
        "message_type": state.message_type,
        "canal": state.canal,
        "connection_id": state.connection_id,
        "bot_id": state.bot_id,
        "bot_name": state.bot_name,
        "contact_phone": state.contact_phone,
        "contact_name": state.contact_name,
        "data": state.data,
    }, default=str)


async def _log_step(
    run_id: str,
    node_id: str,
    node_type: str,
    input_json: str | None,
    state_after: FlowState | None,
    started_at: str,
    status: str,
) -> None:
    try:
        from pulpo.core import db as _db
        output_json = json.dumps(state_after.data, default=str) if state_after else None
        branch = state_after.data.get("route") if state_after else None
        await _db.log_flow_step(
            run_id=run_id, node_id=node_id, node_type=node_type,
            input_state=input_json, output_state=output_json,
            branch_taken=branch, status=status,
            started_at=started_at,
            ended_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except Exception:
        logger.warning("[engine] error al loguear step %s (non-fatal)", node_id, exc_info=True)


def _build_graph(edges: list[dict]) -> dict[str, list[tuple[str, str | None]]]:
    """
    Grafo de adyacencia: source → [(target, label)].
    label=None → seguir siempre; label="noticias" → solo si state.route == "noticias".
    """
    graph: dict[str, list[tuple[str, str | None]]] = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            label = edge.get("label") or None
            graph.setdefault(source, []).append((target, label))
    return graph


def _enqueue_neighbors(
    graph: dict,
    node_id: str,
    visited: set,
    queue: list,
    current_route: str,
) -> None:
    """
    Agrega vecinos al queue respetando labels de edges.
    - Sin label → siempre seguir
    - Con label → solo seguir si current_route == label
    """
    for target, label in graph.get(node_id, []):
        if target in visited:
            continue
        if label is None or label == "" or current_route == label:
            queue.append(target)


async def _run_bfs(
    entry_id: str,
    node_by_id: dict[str, dict],
    graph: dict,
    state: FlowState,
    run_id: str | None = None,
) -> FlowState:
    """
    Ejecuta los nodos en BFS desde entry_id. Cada nodo se visita una sola vez
    (los ciclos no re-ejecutan). Un nodo que falla no aborta el flow: el error
    se loguea con stack trace y queda en state.vars["_node_errors"].
    Si run_id está presente, cada nodo loguea input/output en flow_run_steps (ADR-006).
    """
    # Precalcular in-degree para que el gate sepa cuántas flechas le entran.
    in_degree: dict[str, int] = {}
    for targets in graph.values():
        for tgt, _ in targets:
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

    visited: set[str] = set()
    queue = [entry_id]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        node_def = node_by_id.get(current_id)
        if not node_def:
            continue

        node_type = node_def.get("type", "")
        node_id = node_def.get("id", "")

        # Saltar marcadores visuales — pero seguir sus edges
        if node_id in ("__start__", "__end__") or node_type in ("start", "end"):
            _enqueue_neighbors(graph, current_id, visited, queue, state.data.get("route", ""))
            continue

        node_cls = NODE_REGISTRY.get(node_type)
        if not node_cls:
            logger.debug("[engine] tipo '%s' no tiene implementación — skip", node_type)
            # Seguir edges igual: no abandonar el árbol por un nodo no implementado
            _enqueue_neighbors(graph, current_id, visited, queue, state.data.get("route", ""))
            continue

        step_started = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        input_json = json.dumps(state.data, default=str) if run_id else None
        gate_blocked = False
        try:
            config = {**node_def.get("config", {}), "_node_id": current_id,
                      "_in_degree": in_degree.get(current_id, 1)}
            node = node_cls(config)
            state = await node.run(state)
            gate_blocked = bool(state.data.pop("_gate_blocked", False))
            if gate_blocked:
                state.data["_has_waiting_gate"] = True
                if run_id and node_type == "gate":
                    from .nodes.gate import _store_waiting_run
                    _store_waiting_run(node_id, state.contact_phone or "", run_id)
            elif node_type == "gate" and run_id:
                # Gate acaba de abrirse — cerrar el run que quedó en waiting_gate
                from .nodes.gate import _pop_waiting_run
                waiting_run_id = _pop_waiting_run(node_id, state.contact_phone or "")
                if waiting_run_id and waiting_run_id != run_id:
                    try:
                        from pulpo.core import db as _db
                        await _db.end_flow_run(waiting_run_id, "completed")
                    except Exception:
                        logger.warning("[engine] error cerrando waiting_gate run %s", waiting_run_id, exc_info=True)
            logger.debug("[engine] nodo '%s' (%s) ejecutado%s", node_id, node_type,
                         " [bloqueado]" if gate_blocked else "")
            if run_id:
                status = "blocked" if gate_blocked else "ok"
                await _log_step(run_id, node_id, node_type, input_json, state, step_started, status)
        except Exception as e:
            logger.exception("[engine] Error en nodo '%s' (%s)", node_id, node_type)
            if run_id:
                await _log_step(run_id, node_id, node_type, input_json, None, step_started, "error")
            state.data.setdefault("_node_errors", []).append(
                {"node": node_id, "type": node_type, "error": str(e)}
            )

        if not gate_blocked:
            _enqueue_neighbors(graph, current_id, visited, queue, state.data.get("route", ""))

    errors = state.data.get("_node_errors")
    if errors:
        logger.warning("[engine] Flow terminó con %d error(es): %s", len(errors),
                       [e["node"] for e in errors])
    return state


async def execute_flow(
    flow: dict,
    state: FlowState,
    entry_node_id: str | None = None,
) -> FlowState:
    """
    Ejecuta el flow si su trigger aplica al mensaje.

    entry_node_id: si se pasa, bypasea select_trigger y entra directamente
    desde ese nodo (usado por el endpoint de api_trigger).

    Punto de entrada normal:
      - triggers (TRIGGER_TYPES): canal, connection_id, contactos y regex
        se verifican en trigger_match.select_trigger()
      - __start__: legacy, sin triggers — contact_phone se verifica desde DB

    Los nodos __start__ y __end__ son marcadores visuales — no se ejecutan.
    """
    definition = flow.get("definition", {})
    nodes = definition.get("nodes", [])
    node_by_id = {node["id"]: node for node in nodes}
    graph = _build_graph(definition.get("edges", []))

    if entry_node_id is not None:
        if entry_node_id not in node_by_id:
            logger.debug("[engine] entry_node_id '%s' no encontrado en el flow", entry_node_id)
            return state

        run_id: str | None = str(uuid.uuid4())
        try:
            from pulpo.core import db as _db
            await _db.start_flow_run(
                run_id=run_id,
                flow_id=flow.get("id", ""),
                bot_id=state.bot_id or flow.get("bot_id", ""),
                connection_id=state.connection_id or None,
                trigger_data=_serialize_state(state),
            )
        except Exception:
            logger.warning("[engine] error al crear flow_run para api_trigger (non-fatal)", exc_info=True)
            run_id = None

        result = await _run_bfs(entry_node_id, node_by_id, graph, state, run_id=run_id)

        if run_id:
            try:
                from pulpo.core import db as _db
                errors = result.data.get("_node_errors")
                waiting = result.data.pop("_has_waiting_gate", False)
                final_status = "error" if errors else ("waiting_gate" if waiting else "completed")
                await _db.end_flow_run(run_id, final_status)
            except Exception:
                logger.warning("[engine] error al cerrar flow_run de api_trigger (non-fatal)", exc_info=True)

        return result

    has_triggers = any(n.get("type", "") in TRIGGER_TYPES for n in nodes)

    if has_triggers:
        match = await select_trigger(nodes, state)
        if match is None:
            logger.debug("[engine] Flow sin trigger aplicable (canal=%s, connection=%s) — skip",
                         state.canal, state.connection_id)
            return state

        hours = cooldown_hours(match.config, match.type)
        if flow_cooldown.is_active(flow.get("id", ""), state.contact_phone or "", hours):
            logger.debug("[engine] Cooldown activo para flow '%s' / contacto '%s' — skip",
                         flow.get("name", flow.get("id", "")), state.contact_phone)
            return state

        entry_id = match.node["id"]
    else:
        # Compatibilidad hacia atrás: sin triggers → usar __start__
        if "__start__" not in node_by_id:
            logger.debug("[engine] Flow sin trigger ni __start__ — skip")
            return state
        db_contact = flow.get("contact_phone")
        if db_contact and db_contact != state.contact_phone:
            logger.debug("[engine] Flow (__start__) no aplica: contact_phone DB %s != %s",
                         db_contact, state.contact_phone)
            return state
        entry_id = "__start__"

    # ─── Journal: crear run antes de ejecutar (ADR-006) ──────────────────────
    run_id: str | None = str(uuid.uuid4())
    try:
        from pulpo.core import db as _db
        await _db.start_flow_run(
            run_id=run_id,
            flow_id=flow.get("id", ""),
            bot_id=state.bot_id or flow.get("bot_id", ""),
            connection_id=state.connection_id or None,
            trigger_data=_serialize_state(state),
        )
    except Exception:
        logger.warning("[engine] error al crear flow_run (non-fatal)", exc_info=True)
        run_id = None
    # ─────────────────────────────────────────────────────────────────────────

    result = await _run_bfs(entry_id, node_by_id, graph, state, run_id=run_id)

    if run_id:
        try:
            from pulpo.core import db as _db
            errors = result.data.get("_node_errors")
            waiting = result.data.pop("_has_waiting_gate", False)
            final_status = "error" if errors else ("waiting_gate" if waiting else "completed")
            await _db.end_flow_run(run_id, final_status)
        except Exception:
            logger.warning("[engine] error al cerrar flow_run (non-fatal)", exc_info=True)

    return result


async def resolve_flows(bot_id: str) -> list[dict]:
    """
    Retorna todos los flows activos de la bot.
    El filtrado por connection_id y contact_phone lo hace execute_flow().
    """
    from pulpo.core import db
    from pulpo.core.db import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            db.text("""
                SELECT id, bot_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
                FROM flows
                WHERE bot_id = :bot_id
                  AND active = 1
                ORDER BY created_at
            """),
            {"bot_id": bot_id},
        )).fetchall()
    return [db._flow_row_to_dict(r, include_definition=True) for r in rows]


def _reply_disabled(connection_id: str) -> bool:
    """
    Kill switch global o por conexión.
    DISABLE_AUTO_REPLY=true → nadie manda nada.
    DISABLE_AUTO_REPLY_PHONES=num1,num2 → esas conexiones no mandan nada.
    Solo se chequea connection_id (el bot que envía), nunca contact_phone:
    un teléfono puede ser conexión en una bot y contacto en otra —
    no se deben mezclar roles.
    """
    global_off = os.getenv("DISABLE_AUTO_REPLY", "false").lower() == "true"
    blocked = {n.strip() for n in os.getenv("DISABLE_AUTO_REPLY_PHONES", "").split(",") if n.strip()}
    return global_off or (connection_id in blocked)


def _message_predates_flow(state: FlowState, flow: dict) -> bool:
    """
    Guard: no responder mensajes anteriores a la creación del flow
    (equivalente al activated_at del sistema de herramientas).
    """
    if not state.timestamp:
        return False
    try:
        flow_created = datetime.strptime(flow["created_at"], "%Y-%m-%d %H:%M:%S")
        return state.timestamp < flow_created
    except (ValueError, KeyError):
        return False  # sin created_at o formato raro: ejecutar igual (safe default)


async def run_flows(
    state: FlowState,
    connection_id: str,
) -> FlowState:
    """
    Punto de entrada principal para los adapters.

    1. Encuentra las bots dueñas de este connection_id
    2. Para cada bot: resuelve sus flows activos y los ejecuta
    3. Primer reply no-None gana; todos los nodos sin reply (ej: SummarizeNode) corren igual

    Retorna el FlowState con reply si algún nodo lo produjo.
    """
    from pulpo.core.config import get_bots_for_connection, load_config
    from pulpo.core.paused import is_paused

    bot_ids = get_bots_for_connection(connection_id)
    logger.debug("[engine] run_flows: connection=%s contact=%s bots=%s",
                 connection_id, state.contact_phone, bot_ids)
    if not bot_ids:
        return state

    # Asegurar que state.connection_id esté seteado para que execute_flow pueda filtrar
    if not state.connection_id:
        state.connection_id = connection_id

    disable_reply = _reply_disabled(connection_id)

    for bot_id in bot_ids:
        state.bot_id = bot_id

        config = load_config()
        bot_entry = next((e for e in config.get("bots", []) if e["id"] == bot_id), {})
        if not state.bot_name:
            state.bot_name = bot_entry.get("name", bot_id)

        flows = await resolve_flows(bot_id)

        # Bot pausado — la conexión sigue viva pero no genera replies.
        # Se ejecuta igual sobre una copia para que summarize y otros
        # efectos de lado sigan funcionando.
        if is_paused(bot_id):
            logger.info("[engine] Bot pausado: %s — flows ejecutados sin reply", bot_id)
            state_copy = FlowState(**{f: getattr(state, f) for f in state.__dataclass_fields__})
            state_copy.data = copy.deepcopy(state.data)
            state_copy.from_delta_sync = True  # bloquea replies en todos los nodos
            for flow in flows:
                state_copy.bot_id = bot_id
                state_copy.bot_name = state.bot_name
                await execute_flow(flow, state_copy)
            continue

        for flow in flows:
            if _message_predates_flow(state, flow):
                logger.debug("[engine] Mensaje anterior a flow '%s' (msg:%s) — skip",
                             flow["name"], state.timestamp)
                continue

            prev_reply = state.data.get("reply")
            state = await execute_flow(flow, state)
            # Si este flow generó un reply nuevo, registrar timestamp para cooldown
            if state.data.get("reply") and state.data.get("reply") != prev_reply:
                entry = next(
                    (n for n in flow.get("definition", {}).get("nodes", [])
                     if n.get("type") in TRIGGER_TYPES),
                    None,
                )
                if entry:
                    ch = cooldown_hours(entry.get("config") or {}, entry.get("type", ""))
                    if ch > 0:
                        flow_cooldown.mark(flow["id"], state.contact_phone or "")

    if disable_reply and state.data.get("reply") is not None:
        logger.info("[engine] Kill switch activado — reply descartado (connection_id=%s)",
                    connection_id)
        state.data.pop("reply", None)

    return state
