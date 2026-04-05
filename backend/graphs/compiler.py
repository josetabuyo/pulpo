"""
Flow Engine — el motor que ejecuta flows.

Responsabilidades:
  - resolve_flows(): encuentra los flows activos para un (bot_id, contact, empresa)
  - execute_flow(): corre los nodos de un flow en secuencia
  - run_flows(): orquesta ambos y devuelve (reply, image_url)

Los adapters (WA, Telegram, Sim) normalizan el mensaje a FlowState
y llaman a run_flows(). El engine no sabe nada de protocolos.
"""
import logging
import os
from datetime import datetime
from .nodes.state import FlowState
from .nodes import NODE_REGISTRY

logger = logging.getLogger(__name__)


async def execute_flow(flow: dict, state: FlowState) -> FlowState:
    """
    Ejecuta el flow siguiendo edges en BFS desde el nodo de entrada.

    Punto de entrada:
      - message_trigger: verifica connection_id, contact_phone y message_pattern
      - __start__: legacy (connection_id ya verificado por DB)

    Los nodos __start__ y __end__ son marcadores visuales — no se ejecutan.
    """
    definition = flow.get("definition", {})
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    # Construir mapeo id → nodo
    node_by_id = {node["id"]: node for node in nodes}

    # Construir grafo de adyacencia
    graph = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            graph.setdefault(source, []).append(target)

    # Encontrar nodo de entrada (message_trigger)
    entry_node = None
    for node in nodes:
        node_type = node.get("type", "")
        if node_type == "message_trigger":
            entry_node = node
            break

    # Compatibilidad hacia atrás: si no hay trigger, usar __start__
    if not entry_node:
        for node in nodes:
            if node.get("id") == "__start__":
                entry_node = node
                break

    if not entry_node:
        logger.debug("[engine] Flow sin nodo de entrada (trigger o __start__) — skip")
        return state

    # Verificar si el flow aplica a este mensaje
    entry_type = entry_node.get("type", "")
    entry_config = entry_node.get("config", {})

    if entry_type == "message_trigger":
        # Verificar connection_id — debe estar configurado en el nodo
        required_connection = entry_config.get("connection_id", "")
        if not required_connection:
            logger.debug("[engine] message_trigger sin connection_id configurado — flow ignorado")
            return state
        if required_connection != state.connection_id:
            logger.debug("[engine] Flow no aplica: connection_id %s != %s",
                        required_connection, state.connection_id)
            return state

        # Verificar contact_phone (si está especificado)
        required_contact = entry_config.get("contact_phone", "")
        if required_contact and required_contact != state.contact_phone:
            logger.debug("[engine] Flow no aplica: contact_phone %s != %s",
                        required_contact, state.contact_phone)
            return state

        # Verificar message_pattern (regex opcional)
        pattern = entry_config.get("message_pattern", "")
        if pattern and state.message:
            import re
            try:
                if not re.search(pattern, state.message, re.IGNORECASE):
                    logger.debug("[engine] Flow no aplica: mensaje no matchea pattern '%s'", pattern)
                    return state
            except re.error:
                logger.warning("[engine] Regex inválido en message_pattern: '%s'", pattern)
                # Si el regex es inválido, ignorar el filtro (safe default)
    else:
        # __start__: connection_id ya fue verificado por la DB
        # Solo necesitamos verificar contact_phone si está en la DB
        db_contact = flow.get("contact_phone")
        if db_contact and db_contact != state.contact_phone:
            logger.debug("[engine] Flow (__start__) no aplica: contact_phone DB %s != %s",
                        db_contact, state.contact_phone)
            return state

    # Ejecutar BFS desde el nodo de entrada
    visited = set()
    queue = [entry_node["id"]]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        # Obtener definición del nodo actual
        node_def = node_by_id.get(current_id)
        if not node_def:
            continue

        node_type = node_def.get("type", "")
        node_id = node_def.get("id", "")

        # Saltar marcadores visuales
        if node_id in ("__start__", "__end__"):
            # Pero seguir recorriendo sus edges
            if current_id in graph:
                for neighbor in graph[current_id]:
                    if neighbor not in visited:
                        queue.append(neighbor)
            continue

        # Ejecutar nodo si tiene implementación
        node_cls = NODE_REGISTRY.get(node_type)
        if not node_cls:
            logger.debug("[engine] tipo '%s' no tiene implementación — skip", node_type)
            continue

        try:
            node = node_cls(node_def.get("config", {}))
            state = await node.run(state)
        except Exception as e:
            logger.error("[engine] Error en nodo '%s' (%s): %s", node_id, node_type, e)

        # Agregar vecinos al queue
        if current_id in graph:
            for neighbor in graph[current_id]:
                if neighbor not in visited:
                    queue.append(neighbor)

    return state


async def resolve_flows(empresa_id: str) -> list[dict]:
    """
    Retorna todos los flows activos de la empresa.
    El filtrado por connection_id y contact_phone ahora lo hace execute_flow().
    """
    import db
    from db import AsyncSessionLocal, text
    # Obtener TODOS los flows activos de la empresa, sin filtrar por connection_id
    # El filtrado se hace en execute_flow() usando la configuración del message_trigger
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            db.text("""
                SELECT id, empresa_id, name, definition, connection_id, contact_phone, active, created_at, updated_at
                FROM flows
                WHERE empresa_id = :empresa_id
                  AND active = 1
                ORDER BY created_at
            """),
            {"empresa_id": empresa_id},
        )).fetchall()
    return [db._flow_row_to_dict(r, include_definition=True) for r in rows]


async def run_flows(
    state: FlowState,
    connection_id: str,
) -> FlowState:
    """
    Punto de entrada principal para los adapters.

    1. Encuentra las empresas dueñas de este connection_id
    2. Para cada empresa: resuelve sus flows activos y los ejecuta
    3. Primer reply no-None gana; todos los nodos sin reply (ej: SummarizeNode) corren igual

    Retorna el FlowState con reply y image_url si algún nodo los produjo.
    """
    from config import get_empresas_for_connection, load_config

    empresa_ids = get_empresas_for_connection(connection_id)
    if not empresa_ids:
        return state

    # Asegurar que state.connection_id esté seteado para que execute_flow pueda filtrar
    if not state.connection_id:
        state.connection_id = connection_id

    # Kill switch global o por número.
    # DISABLE_AUTO_REPLY=true → nadie manda nada.
    # DISABLE_AUTO_REPLY_PHONES=num1,num2 → esos números no mandan nada.
    _global_off   = os.getenv("DISABLE_AUTO_REPLY", "false").lower() == "true"
    _blocked_nums = {n.strip() for n in os.getenv("DISABLE_AUTO_REPLY_PHONES", "").split(",") if n.strip()}
    disable_reply = _global_off or (connection_id in _blocked_nums) or (state.contact_phone in _blocked_nums)

    for empresa_id in empresa_ids:
        state.empresa_id = empresa_id

        # Obtener nombre de la empresa para contexto del LLM
        config = load_config()
        empresa_entry = next((e for e in config.get("empresas", []) if e["id"] == empresa_id), {})
        if not state.bot_name:
            state.bot_name = empresa_entry.get("name", empresa_id)

        flows = await resolve_flows(empresa_id)

        for flow in flows:
            # Guard: no responder mensajes anteriores a la creación del flow
            # (equivalente al activated_at del sistema de herramientas)
            if state.timestamp:
                try:
                    flow_created = datetime.strptime(flow["created_at"], "%Y-%m-%d %H:%M:%S")
                    if state.timestamp < flow_created:
                        logger.debug(
                            "[engine] Mensaje anterior a flow '%s' (msg:%s < flow:%s) — skip",
                            flow["name"], state.timestamp, flow_created,
                        )
                        continue
                except (ValueError, KeyError):
                    pass  # sin created_at o formato raro: ejecutar igual (safe default)

            state = await execute_flow(flow, state)

    if disable_reply:
        logger.info(f"[engine] Kill switch activado — reply descartado (global_off={_global_off}, connection_id={connection_id} in blocked={connection_id in _blocked_nums}, contact={state.contact_phone} in blocked={state.contact_phone in _blocked_nums})")
        state.reply = None
        state.image_url = None

    return state
