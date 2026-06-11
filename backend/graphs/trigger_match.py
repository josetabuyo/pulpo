"""
Selección de trigger — decide si un flow aplica al mensaje entrante.

Toda la lógica de "¿este trigger matchea?" vive acá: canal, connection_id,
filtro de contactos (con enforcement de allow_mass) y regex del mensaje.
El engine (compiler.py) solo orquesta.

Los imports de db/config son lazy (dentro de funciones) para evitar ciclos
y para que estos helpers sean testeables con monkeypatch sin server.
"""
import logging
import re
from dataclasses import dataclass

from .nodes import NODE_REGISTRY, TRIGGER_TYPES
from .nodes.state import FlowState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TriggerMatch:
    """Trigger que aplica al mensaje: nodo de entrada del BFS + su config."""
    node: dict
    type: str
    config: dict


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
    Dado un valor del filtro (nombre o número/chat_id), devuelve el set de valores que representa.
    - Si parece número (solo dígitos, 7-15 chars): devuelve {value}
    - Si parece nombre: busca los contactos con ese nombre y devuelve sus chat_ids de Telegram
    """
    if re.match(r'^\d{7,15}$', value.strip()):
        return {value.strip()}
    # Es un nombre — buscar sus canales Telegram
    from db import get_contacts
    contacts = await get_contacts(empresa_id)
    ids: set[str] = set()
    for c in contacts:
        if c["name"] == value:
            for ch in c.get("channels", []):
                if ch["type"] == "telegram":
                    ids.add(ch["value"])
    return ids


def _matches_channel(trigger_type: str, state: FlowState) -> bool:
    """El canal del mensaje debe coincidir con el canal del trigger (None = cualquiera)."""
    node_cls = NODE_REGISTRY.get(trigger_type)
    channel = getattr(node_cls, "channel", None)
    if channel and state.canal != channel:
        logger.debug("[engine] %s no aplica: canal '%s' != '%s'", trigger_type, state.canal, channel)
        return False
    return True


def _mass_send_allowed(connection_id: str, empresa_id: str) -> bool:
    """
    True si la conexión tiene allow_mass en connections.json.
    Backend enforcement: include_all_known / include_unknown son opciones masivas;
    la UI ya las oculta sin allow_mass, pero esto es defensa en profundidad
    (alguien puede editar la DB a mano).
    """
    from config import load_config
    for emp in load_config().get("empresas", []):
        if empresa_id and emp["id"] != empresa_id:
            continue
        for ph in emp.get("phones", []):
            if ph.get("number") == connection_id and ph.get("allow_mass", False):
                return True
        for tg in emp.get("telegram", []):
            tok_id = tg.get("token", "").split(":")[0]
            if f"{emp['id']}-tg-{tok_id}" == connection_id and tg.get("allow_mass", False):
                return True
    return False


async def _passes_contact_filter(cconfig: dict, state: FlowState) -> bool:
    """
    Aplica el contact_filter del trigger (o el default de la conexión).
    Sin filtro cae al modo legacy: contact_phone exacto del config.
    """
    contact_filter = cconfig.get("contact_filter")
    if contact_filter is None:
        from config import get_connection_default_filter
        default_cf = get_connection_default_filter(cconfig.get("connection_id", ""), state.empresa_id)
        if default_cf:
            contact_filter = default_cf

    if not contact_filter:
        # Legacy: contact_phone exacto
        required_contact = cconfig.get("contact_phone", "")
        if required_contact and required_contact != state.contact_phone:
            logger.debug("[engine] Trigger no aplica: contact_phone %s != %s",
                         required_contact, state.contact_phone)
            return False
        return True

    excluded = contact_filter.get("excluded", [])
    included = contact_filter.get("included", [])
    inc_all  = contact_filter.get("include_all_known", False)
    inc_unk  = contact_filter.get("include_unknown", False)
    empresa  = state.empresa_id or ""

    if (inc_all or inc_unk) and not _mass_send_allowed(cconfig.get("connection_id", ""), empresa):
        inc_all = False
        inc_unk = False
        logger.warning(
            "[engine] inc_all/inc_unk ignorados: allow_mass=false para conexión %s",
            cconfig.get("connection_id", ""),
        )

    excluded_phones: set[str] = set()
    for v in excluded:
        excluded_phones |= await _resolve_filter_value(v, empresa)

    included_phones: set[str] = set()
    for v in included:
        included_phones |= await _resolve_filter_value(v, empresa)

    if state.contact_phone in excluded_phones or state.contact_phone in excluded:
        logger.debug("[engine] Trigger no aplica: contacto %s excluido", state.contact_phone)
        return False

    logger.debug("[engine] filter check: contact=%r included=%r included_phones=%r",
                 state.contact_phone, included, included_phones)
    if state.contact_phone in included_phones or state.contact_phone in included:
        return True
    if inc_all or inc_unk:
        is_known = await _is_known_contact(state.contact_phone, state.empresa_id or "")
        if inc_all and is_known:
            return True
        if inc_unk and not is_known:
            return True

    logger.debug("[engine] Trigger no aplica: contacto %s no en ninguna lista de inclusión",
                 state.contact_phone)
    return False


def _matches_pattern(pattern: str, message: str) -> bool:
    """Regex opcional sobre el mensaje. Una regex inválida no bloquea el flow."""
    if not pattern or not message:
        return True
    try:
        return re.search(pattern, message, re.IGNORECASE) is not None
    except re.error:
        logger.warning("[engine] Regex inválido en message_pattern: '%s'", pattern)
        return True


async def select_trigger(nodes: list[dict], state: FlowState) -> TriggerMatch | None:
    """
    Devuelve el primer trigger del flow que aplica al estado, o None.
    Orden de filtros: canal → connection_id → contactos → regex.
    """
    candidates = [n for n in nodes if n.get("type", "") in TRIGGER_TYPES]
    for candidate in candidates:
        ctype = candidate.get("type", "")
        cconfig = candidate.get("config", {})

        if not _matches_channel(ctype, state):
            continue

        required_connection = cconfig.get("connection_id", "")
        if not required_connection:
            logger.debug("[engine] trigger sin connection_id configurado — skip")
            continue
        if required_connection != state.connection_id:
            logger.debug("[engine] Flow no aplica: connection_id %s != %s",
                         required_connection, state.connection_id)
            continue

        if not await _passes_contact_filter(cconfig, state):
            continue

        if not _matches_pattern(cconfig.get("message_pattern", ""), state.message):
            logger.debug("[engine] Trigger no aplica: mensaje no matchea pattern '%s'",
                         cconfig.get("message_pattern", ""))
            continue

        return TriggerMatch(node=candidate, type=ctype, config=cconfig)

    return None
