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
import logging
import os
from datetime import datetime

from .cooldown import cooldown_hours, flow_cooldown
from .nodes import NODE_REGISTRY, TRIGGER_TYPES
from .nodes.state import FlowState
from .trigger_match import select_trigger

logger = logging.getLogger(__name__)


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
) -> FlowState:
    """
    Ejecuta los nodos en BFS desde entry_id. Cada nodo se visita una sola vez
    (los ciclos no re-ejecutan). Un nodo que falla no aborta el flow: el error
    se loguea con stack trace y queda en state.vars["_node_errors"].
    """
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
            _enqueue_neighbors(graph, current_id, visited, queue, state.route)
            continue

        node_cls = NODE_REGISTRY.get(node_type)
        if not node_cls:
            logger.debug("[engine] tipo '%s' no tiene implementación — skip", node_type)
            # Seguir edges igual: no abandonar el árbol por un nodo no implementado
            _enqueue_neighbors(graph, current_id, visited, queue, state.route)
            continue

        try:
            node = node_cls(node_def.get("config", {}))
            state = await node.run(state)
            logger.debug("[engine] nodo '%s' (%s) ejecutado", node_id, node_type)
        except Exception as e:
            logger.exception("[engine] Error en nodo '%s' (%s)", node_id, node_type)
            state.vars.setdefault("_node_errors", []).append(
                {"node": node_id, "type": node_type, "error": str(e)}
            )

        _enqueue_neighbors(graph, current_id, visited, queue, state.route)

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
        return await _run_bfs(entry_node_id, node_by_id, graph, state)

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

    return await _run_bfs(entry_id, node_by_id, graph, state)


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

            prev_reply = state.reply
            state = await execute_flow(flow, state)
            # Si este flow generó un reply nuevo, registrar timestamp para cooldown
            if state.reply and state.reply != prev_reply:
                entry = next(
                    (n for n in flow.get("definition", {}).get("nodes", [])
                     if n.get("type") in TRIGGER_TYPES),
                    None,
                )
                if entry:
                    ch = cooldown_hours(entry.get("config") or {}, entry.get("type", ""))
                    if ch > 0:
                        flow_cooldown.mark(flow["id"], state.contact_phone or "")

    if disable_reply and state.reply is not None:
        logger.info("[engine] Kill switch activado — reply descartado (connection_id=%s)",
                    connection_id)
        state.reply = None

    return state
