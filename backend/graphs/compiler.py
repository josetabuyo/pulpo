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
from datetime import datetime
from .nodes.state import FlowState
from .nodes import NODE_REGISTRY

logger = logging.getLogger(__name__)


async def execute_flow(definition: dict, state: FlowState) -> FlowState:
    """
    Ejecuta los nodos de un flow en orden secuencial.
    Los nodos __start__ y __end__ son marcadores visuales — no se ejecutan.
    Fase 3 agregará routing condicional usando los edges.
    """
    for node_def in definition.get("nodes", []):
        node_id = node_def.get("id", "")
        if node_id in ("__start__", "__end__"):
            continue

        node_type = node_def.get("type", "")
        node_cls = NODE_REGISTRY.get(node_type)
        if not node_cls:
            logger.debug("[engine] tipo '%s' no tiene implementación — skip", node_type)
            continue

        try:
            node = node_cls(node_def.get("config", {}))
            state = await node.run(state)
        except Exception as e:
            logger.error("[engine] Error en nodo '%s' (%s): %s", node_id, node_type, e)

    return state


async def resolve_flows(bot_id: str, contact_phone: str, empresa_id: str) -> list[dict]:
    """
    Retorna los flows activos para este (bot_id, contact, empresa), con su definition.
    Orden de especificidad: connection+contact > solo connection > sin filtro.
    """
    import db
    return await db.get_active_flows_for_bot(bot_id, contact_phone, empresa_id)


async def run_flows(
    state: FlowState,
    bot_id: str,
) -> FlowState:
    """
    Punto de entrada principal para los adapters.

    1. Encuentra las empresas dueñas de este bot_id
    2. Para cada empresa: resuelve sus flows activos y los ejecuta
    3. Primer reply no-None gana; todos los nodos sin reply (ej: SummarizeNode) corren igual

    Retorna el FlowState con reply y image_url si algún nodo los produjo.
    """
    from config import get_empresas_for_bot, load_config

    empresa_ids = get_empresas_for_bot(bot_id)
    if not empresa_ids:
        return state

    for empresa_id in empresa_ids:
        state.empresa_id = empresa_id

        # Obtener nombre de la empresa para contexto del LLM
        config = load_config()
        bot_entry = next((b for b in config.get("bots", []) if b["id"] == empresa_id), {})
        if not state.bot_name:
            state.bot_name = bot_entry.get("name", empresa_id)

        flows = await resolve_flows(bot_id, state.contact_phone, empresa_id)

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

            state = await execute_flow(flow["definition"], state)

    return state
