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
import time as _time
from datetime import datetime
from .nodes.state import FlowState
from .nodes import NODE_REGISTRY

logger = logging.getLogger(__name__)

# Cooldown por flow: (flow_id, contact_phone) → timestamp del último reply enviado.
# Persiste en memoria mientras el backend esté corriendo.
_flow_cooldown: dict[tuple[str, str], float] = {}


async def _is_known_contact(contact_phone: str, empresa_id: str) -> bool:
    """True si contact_phone está registrado en contact_channels de esta empresa."""
    from db import AsyncSessionLocal, text as _text
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            _text("""
                SELECT cc.id FROM contact_channels cc
                JOIN contacts c ON cc.contact_id = c.id
                WHERE cc.value = :phone
                  AND c.connection_id = :empresa_id
                LIMIT 1
            """),
            {"phone": contact_phone, "empresa_id": empresa_id},
        )).fetchone()
    return row is not None


async def _resolve_filter_value(value: str, empresa_id: str) -> set[str]:
    """
    Dado un valor del filtro (nombre o número), devuelve el set de teléfonos que representa.
    - Si parece número (solo dígitos, 7-15 chars): devuelve {value}
    - Si parece nombre: busca los contactos con ese nombre y devuelve sus phones WA
    """
    import re
    if re.match(r'^\d{7,15}$', value.strip()):
        return {value.strip()}
    # Es un nombre — buscar sus canales WA
    from db import get_contacts
    contacts = await get_contacts(empresa_id)
    phones: set[str] = set()
    for c in contacts:
        if c["name"] == value:
            for ch in c.get("channels", []):
                if ch["type"] == "whatsapp":
                    phones.add(ch["value"])
    return phones


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

    # Construir grafo de adyacencia: source → [(target, label)]
    # label=None → seguir siempre; label="noticias" → solo si state.route == "noticias"
    graph: dict[str, list[tuple[str, str | None]]] = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            label = edge.get("label") or None
            graph.setdefault(source, []).append((target, label))

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

        # Verificar filtro de contactos
        contact_filter = entry_config.get("contact_filter")
        # Herencia: si el trigger no tiene contact_filter, heredar el default de la conexión
        if contact_filter is None:
            from config import get_connection_default_filter
            default_cf = get_connection_default_filter(entry_config.get("connection_id", ""))
            if default_cf:
                contact_filter = default_cf
        if contact_filter:
            # Nuevo sistema: flags combinables
            # include_all_known: responde a todos los contactos registrados
            # include_unknown:   responde a contactos no registrados
            # included:          lista específica de phones a incluir
            # excluded:          lista de phones a siempre excluir (prioridad máxima)
            excluded  = contact_filter.get("excluded", [])
            included  = contact_filter.get("included", [])
            inc_all   = contact_filter.get("include_all_known", False)
            inc_unk   = contact_filter.get("include_unknown", False)
            empresa   = state.empresa_id or ""

            # Resolver cada valor (nombre o número) al set de teléfonos reales
            excluded_phones: set[str] = set()
            for v in excluded:
                excluded_phones |= await _resolve_filter_value(v, empresa)

            included_phones: set[str] = set()
            for v in included:
                included_phones |= await _resolve_filter_value(v, empresa)

            # 1. Excluidos tienen prioridad absoluta
            # Chequear tanto por teléfono resuelto como por valor literal (nombre o número tal cual llega de WA)
            if state.contact_phone in excluded_phones or state.contact_phone in excluded:
                logger.debug("[engine] Flow no aplica: contacto %s está excluido", state.contact_phone)
                return state

            # 2. Evaluar si el contacto está incluido
            is_allowed = False

            logger.debug("[engine] filter check: contact=%r included=%r included_phones=%r",
                         state.contact_phone, included, included_phones)

            # Chequear por teléfono resuelto Y por valor literal (por si WA entrega el nombre en lugar del número)
            if state.contact_phone in included_phones or state.contact_phone in included:
                is_allowed = True
            elif inc_all or inc_unk:
                # Necesitamos saber si el contacto es conocido
                is_known = await _is_known_contact(state.contact_phone, state.empresa_id or "")
                if inc_all and is_known:
                    is_allowed = True
                elif inc_unk and not is_known:
                    is_allowed = True

            if not is_allowed:
                logger.debug("[engine] Flow no aplica: contacto %s no está en ninguna lista de inclusión", state.contact_phone)
                return state

        else:
            # Legacy: contact_phone exacto (un solo contacto)
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

    # Cooldown: si el trigger tiene cooldown_hours configurado, verificar
    if entry_type == "message_trigger":
        cooldown_hours = float(entry_config.get("cooldown_hours") or 0)
        if cooldown_hours > 0:
            flow_id = flow.get("id", "")
            ck = (str(flow_id), state.contact_phone or "")
            last_sent = _flow_cooldown.get(ck, 0)
            elapsed_h = (_time.time() - last_sent) / 3600
            if elapsed_h < cooldown_hours:
                remaining = cooldown_hours - elapsed_h
                logger.debug(
                    "[engine] Cooldown activo para flow '%s' / contacto '%s' — restan %.1fh",
                    flow.get("name", flow_id), state.contact_phone, remaining,
                )
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

        # Saltar marcadores visuales — pero seguir sus edges
        if node_id in ("__start__", "__end__") or node_type in ("start", "end"):
            _enqueue_neighbors(graph, current_id, visited, queue, state.route)
            continue

        # Ejecutar nodo si tiene implementación
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
            logger.error("[engine] Error en nodo '%s' (%s): %s", node_id, node_type, e)

        _enqueue_neighbors(graph, current_id, visited, queue, state.route)

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
                SELECT id, empresa_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
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
    logger.debug("[engine] run_flows: connection=%s contact=%s empresas=%s",
                 connection_id, state.contact_phone, empresa_ids)
    if not empresa_ids:
        return state

    # Asegurar que state.connection_id esté seteado para que execute_flow pueda filtrar
    if not state.connection_id:
        state.connection_id = connection_id

    # Kill switch global o por número.
    # DISABLE_AUTO_REPLY=true → nadie manda nada.
    # DISABLE_AUTO_REPLY_PHONES=num1,num2 → esas conexiones no mandan nada.
    # Solo se chequea connection_id (el bot que envía), nunca contact_phone.
    # Un teléfono puede ser conexión en una empresa y contacto en otra — no se deben mezclar roles.
    _global_off   = os.getenv("DISABLE_AUTO_REPLY", "false").lower() == "true"
    _blocked_nums = {n.strip() for n in os.getenv("DISABLE_AUTO_REPLY_PHONES", "").split(",") if n.strip()}
    disable_reply = _global_off or (connection_id in _blocked_nums)

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

            prev_reply = state.reply
            state = await execute_flow(flow, state)
            # Si este flow generó un reply nuevo, registrar timestamp para cooldown
            if state.reply and state.reply != prev_reply:
                entry = next(
                    (n for n in flow.get("definition", {}).get("nodes", []) if n.get("type") == "message_trigger"),
                    None,
                )
                if entry:
                    ch = float((entry.get("config") or {}).get("cooldown_hours") or 0)
                    if ch > 0:
                        _flow_cooldown[(str(flow["id"]), state.contact_phone or "")] = _time.time()

    if disable_reply and state.reply is not None:
        logger.info("[engine] Kill switch activado — reply descartado (global_off=%s, connection_id=%s bloqueado=%s)",
                    _global_off, connection_id, connection_id in _blocked_nums)
        state.reply = None
        state.image_url = None

    return state
