"""
Flow Engine — el motor que ejecuta flows.

Responsabilidades:
  - resolve_flows(): encuentra los flows activos de una bot
  - execute_flow(): corre los nodos de UN flow en BFS desde su trigger
  - dispatch_message(): orquesta execute_flow() sobre TODOS los flows de una
    bot para un mensaje entrante, y devuelve el FlowState con reply

Colaboradores:
  - trigger_match.select_trigger(): decide si un trigger aplica al mensaje
  - cooldown.flow_cooldown: rate limit de replies por (flow, contacto)
  - conversation.py: dueño de cuándo un flow acumula data["conversation"]
    (el engine acá es agnóstico a mensajería — ver ese módulo)

Los adapters (Telegram, Wavi, Sim) normalizan el mensaje a FlowState
y llaman a dispatch_message(). El engine no sabe nada de protocolos.
"""
import copy
import json
import logging
import os
import uuid
from datetime import datetime

from . import conversation
from .cooldown import cooldown_hours, flow_cooldown
from .nodes import NODE_REGISTRY, TRIGGER_TYPES, MESSAGE_TRIGGER_TYPES
from .nodes.state import FlowState
from .trigger_match import select_trigger

logger = logging.getLogger(__name__)


def _serialize_state(state: FlowState) -> str:
    payload = {
        "canal": state.canal,
        "connection_id": state.connection_id,
        "bot_id": state.bot_id,
        "bot_name": state.bot_name,
        "contact_phone": state.contact_phone,
        "contact_name": state.contact_name,
        "data": state.data,
    }
    # message/message_type ya viajan como el primer turno de data["conversation"]
    # (ver graphs/conversation.py) — solo se repiten acá si por algún motivo esa
    # conversación no llegó a crearse (state.message vino vacío).
    if "conversation" not in state.data:
        payload["message"] = state.message
        payload["message_type"] = state.message_type
    return json.dumps(payload, default=str)


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
                elif run_id and node_type == "wait_user":
                    # Persistir punto de reanudación en DB
                    neighbors = graph.get(current_id, [])
                    resume_node = neighbors[0][0] if neighbors else None
                    if resume_node:
                        try:
                            from pulpo.core import db as _db
                            await _db.set_wait_user_info(
                                run_id=run_id,
                                contact_phone=state.contact_phone or "",
                                resume_node_id=resume_node,
                                slots_json=json.dumps(state.data, default=str),
                            )
                        except Exception:
                            logger.warning("[engine] error guardando wait_user info (non-fatal)", exc_info=True)
            elif node_type == "gate" and run_id:
                # Gate acaba de abrirse — cerrar el run que quedó en waiting_gate.
                # "handed_off" (no "completed"): ese run nunca llegó a un final natural,
                # quedó bloqueado en el gate — este run nuevo es el que sigue la posta.
                from .nodes.gate import _pop_waiting_run
                waiting_run_id = _pop_waiting_run(node_id, state.contact_phone or "")
                if waiting_run_id and waiting_run_id != run_id:
                    try:
                        from pulpo.core import db as _db
                        await _db.end_flow_run(waiting_run_id, "handed_off")
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

        # Reanudación de wait_user ya llamó continue_conversation() antes de esta
        # llamada (ver dispatch_message) — el guard de start_conversation() la hace
        # no-op ahí. Para api_trigger "puro" (trigger_flow), esto es lo que arranca
        # la conversación de ese run — ver graphs/conversation.py.
        conversation.start_conversation(state)

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
                await _save_open_conversation_if_applicable(result, flow, waiting)
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
        if match.type in MESSAGE_TRIGGER_TYPES:
            conversation.start_conversation(state)
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
        # Legacy: flows sin triggers son de antes de que existieran — siempre
        # fueron message-based (contact_phone en DB), así que son conversación.
        conversation.start_conversation(state)

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
            await _save_open_conversation_if_applicable(result, flow, waiting)
        except Exception:
            logger.warning("[engine] error al cerrar flow_run (non-fatal)", exc_info=True)

    return result


async def _save_open_conversation_if_applicable(state: FlowState, flow: dict, waiting: bool) -> None:
    """
    Conversación abierta más allá del wait_user (Escenarios A+B — ver
    management/NEXT_SESSION_MENSAJES_RAPIDOS.md). Se excluye el caso
    waiting_gate a propósito: ese ya tiene su propio mecanismo de reanudación
    (slots_json + get_waiting_gate_run) — no conviene que compitan dos fuentes
    de verdad para el mismo run. Estado explícito, sin ventana de tiempo: el
    cierre por abandono lo hace un proceso aparte (ver db.prune_open_conversations).
    """
    if waiting or not state.contact_phone:
        return
    if state.data.pop("_conversation_closed", False):
        # end_conversation ya cerró la fila explícitamente en este mismo run —
        # no resucitarla acá solo porque state.data["conversation"] sigue en memoria.
        return
    conv = state.data.get("conversation")
    if not conv:
        return
    from pulpo.core import db as _db
    await _db.save_open_conversation(
        bot_id=state.bot_id or flow.get("bot_id", ""),
        contact_phone=state.contact_phone,
        connection_id=state.connection_id,
        flow_id=flow.get("id", ""),
        conversation_json=json.dumps(conv, default=str),
    )


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


# ── Lock en memoria por (bot_id, contact_phone) ──────────────────────────
# Evita que un segundo mensaje dispare una ejecución PARALELA del mismo flow
# para el mismo contacto mientras la primera sigue corriendo (fuera de
# wait_user, que ya se serializa solo porque el run queda parqueado en DB).
# Un mensaje que llega con el lock tomado no arranca un flow nuevo: se
# acumula en _PENDING_MESSAGES y se despacha en cadena — uno a la vez,
# reusando wait_user/open_conversations para el contexto — apenas se libera
# el lock. Ver management/NEXT_SESSION_MENSAJES_RAPIDOS.md.
_IN_FLIGHT: set[tuple[str, str]] = set()
_PENDING_MESSAGES: dict[tuple[str, str], list[FlowState]] = {}


def _clone_state_for_replay(state: FlowState, bot_id: str) -> FlowState:
    """
    Copia liviana para encolar en _PENDING_MESSAGES: mismos datos de canal/
    contacto/mensaje, pero data={} fresco — nunca comparte el dict mutable
    del state original (que sigue viajando por el resto del loop de bots).
    """
    return FlowState(
        message=state.message,
        message_type=state.message_type,
        attachment_path=state.attachment_path,
        connection_id=state.connection_id,
        bot_name="",
        bot_id=bot_id,
        contact_phone=state.contact_phone,
        contact_name=state.contact_name,
        canal=state.canal,
        from_poll=state.from_poll,
        from_delta_sync=state.from_delta_sync,
        timestamp=state.timestamp,
        group_sender=state.group_sender,
    )


async def dispatch_message(
    state: FlowState,
    connection_id: str,
) -> FlowState:
    """
    Punto de entrada principal para los adapters — UN mensaje entrante,
    despachado sobre TODOS los flows de las bots dueñas de connection_id.

    1. Encuentra las bots dueñas de este connection_id
    2. Para cada bot: resuelve sus flows activos y los ejecuta (execute_flow)
    3. Primer reply no-None gana; todos los nodos sin reply (ej: SummarizeNode) corren igual

    Retorna el FlowState con reply si algún nodo lo produjo.
    """
    from pulpo.core.config import get_bots_for_connection, load_config
    from pulpo.core.paused import is_paused

    bot_ids = get_bots_for_connection(connection_id)
    logger.debug("[engine] dispatch_message: connection=%s contact=%s bots=%s",
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
        state.data.setdefault("_conv_ttl_hours", bot_entry.get("conversation_ttl_hours", 24))

        # ── Dispatcher wait_user: reanudar conversación pausada ──────────────
        # Corre siempre, sin lock: un run parqueado en wait_user ya está
        # serializado por definición (nada está "en vuelo").
        resumed_wait_user = False
        try:
            from pulpo.core import db as _db
            waiting = await _db.get_waiting_gate_run(bot_id, state.contact_phone or "")
            if waiting and waiting.get("resume_node_id"):
                flow = await _db.get_flow(waiting["flow_id"])
                if flow:
                    # Calcular edad de la conversación en minutos
                    started = datetime.strptime(waiting["started_at"], "%Y-%m-%d %H:%M:%S")
                    age_minutes = int((datetime.utcnow() - started).total_seconds() / 60)
                    # Restaurar slots del turno anterior + inyectar nuevo mensaje
                    saved = json.loads(waiting["slots_json"] or "{}")
                    # Preservar claves internas limpias; el mensaje nuevo ya está en state.message
                    saved.pop("_has_waiting_gate", None)
                    saved.pop("_gate_blocked", None)
                    # Resetear contadores de visita si la conversación quedó inactiva >30 min:
                    # evita agotado instantáneo cuando el usuario retoma una sesión antigua.
                    if age_minutes > 30:
                        visits_keys = [k for k in saved if k.startswith("_visits_")]
                        for k in visits_keys:
                            saved.pop(k)
                    state.data.update(saved)
                    # Inyectar metadatos de conversación abierta (después de restaurar slots
                    # para que los metadatos no sean sobreescritos por el estado guardado)
                    state.data["_has_open_conv"] = True
                    state.data["_conv_age_minutes"] = age_minutes
                    state.data["_conv_resume_node"] = waiting.get("resume_node_id", "")
                    # El array conversation viaja dentro de saved (es parte de data) —
                    # acá solo agregamos el turno nuevo que trajo esta reanudación.
                    # Reanudar un wait_user ES por definición continuar una conversación.
                    conversation.continue_conversation(state)
                    # "handed_off" (no "completed"): este run nunca llegó a un final
                    # natural — quedó bloqueado en wait_user y el run nuevo (con
                    # entry_node_id=resume_node_id) es el que sigue la ejecución.
                    await _db.end_flow_run(waiting["run_id"], "handed_off")
                    logger.info("[engine] Reanudando wait_user run=%s desde nodo=%s contacto=%s age=%dm",
                                waiting["run_id"], waiting["resume_node_id"], state.contact_phone, age_minutes)
                    state = await execute_flow(flow, state, entry_node_id=waiting["resume_node_id"])
                    resumed_wait_user = True
        except Exception:
            logger.warning("[engine] error en dispatcher wait_user (non-fatal)", exc_info=True)
        # ─────────────────────────────────────────────────────────────────────
        if resumed_wait_user:
            continue

        # ── Lock en memoria: sin wait_user pendiente, evitar una ejecución
        # paralela del mismo flow para este contacto. Si ya hay una corriendo,
        # este mensaje se acumula (_PENDING_MESSAGES) y se despacha en cadena
        # al liberar — no arranca un flow nuevo acá. Ver _IN_FLIGHT arriba.
        key = (bot_id, state.contact_phone or "")
        if key in _IN_FLIGHT:
            _PENDING_MESSAGES.setdefault(key, []).append(_clone_state_for_replay(state, bot_id))
            logger.info("[engine] mensaje encolado (flow en vuelo) bot=%s contacto=%s",
                        bot_id, state.contact_phone)
            continue

        _IN_FLIGHT.add(key)
        try:
            # Sin wait_user pendiente — ¿hay una conversación abierta igual
            # (el flow terminó normalmente pero la charla sigue viva)? El
            # trigger de mensaje simplemente encola el turno nuevo en esa
            # conversación y deja que el flow siga su curso normal más abajo
            # (execute_flow() no-opea start_conversation() si "conversation"
            # ya está en state.data). Sin ventana de tiempo: es estado
            # explícito, se cierra por end_conversation o por el cron externo
            # de prune_open_conversations — ver management/NEXT_SESSION_MENSAJES_RAPIDOS.md.
            try:
                from pulpo.core import db as _db
                open_conv = await _db.get_open_conversation(bot_id, state.contact_phone or "")
                if open_conv:
                    state.data["conversation"] = json.loads(open_conv["conversation_json"])
                    state.data["_has_open_conv"] = True
                    updated = datetime.strptime(open_conv["updated_at"], "%Y-%m-%d %H:%M:%S")
                    state.data["_conv_age_minutes"] = int((datetime.utcnow() - updated).total_seconds() / 60)
                    conversation.continue_conversation(state)
                else:
                    # Sin conversación abierta — inyectar flag para nodos detect_conversation.
                    # (El primer turno de una conversación nueva lo siembra execute_flow(),
                    # gateado por el tipo de trigger — ver graphs/conversation.py)
                    state.data["_has_open_conv"] = False
            except Exception:
                logger.warning("[engine] error chequeando open_conversation (non-fatal)", exc_info=True)

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
        finally:
            _IN_FLIGHT.discard(key)
            pending = _PENDING_MESSAGES.pop(key, [])
            if pending:
                next_state = pending.pop(0)
                if pending:
                    _PENDING_MESSAGES[key] = pending
                # Encadenar — reusa wait_user/open_conversations para el
                # contexto, no duplica la ejecución del flow que acaba de
                # terminar (o de quedar parqueado en wait_user) acá arriba.
                await dispatch_message(next_state, connection_id=connection_id)

    if disable_reply and state.data.get("reply") is not None:
        logger.info("[engine] Kill switch activado — reply descartado (connection_id=%s)",
                    connection_id)
        state.data.pop("reply", None)

    return state
