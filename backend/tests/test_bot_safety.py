"""
Tests de seguridad anti-spam — nuevas protecciones.

  1. max_age_hours en SendMessageNode
     - Mensaje viejo (> límite) → reply bloqueado
     - Mensaje reciente → reply pasa
     - Sin timestamp → reply pasa (safe default)
     - max_age_hours=0 → desactivado, siempre pasa
     - from_delta_sync → siempre bloqueado (cobertura existente, reafirmada aquí)

  2. Cooldown por flow+contacto (telegram_trigger y whatsapp_trigger)
     - Primer mensaje → reply pasa, cooldown registrado
     - Segundo mensaje dentro del cooldown → reply bloqueado
     - Mismo flow distinto contacto → no afectado
     - Config sin cooldown_hours (flow viejo, campo no guardado) → usa default 0 → sin cooldown
       (el fix real está en el frontend: dbNodeToRF mezcla DEFAULT_CONFIGS)

  3. Pausa por empresa (paused.py)
     - pause() → is_paused() True
     - resume() → is_paused() False
     - run_flows con empresa pausada → reply None, flow se ejecutó igual

Tests unitarios puros — no requieren servidor corriendo.
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from graphs.nodes.reply import SendMessageNode
from graphs.nodes.state import FlowState
from graphs.compiler import run_flows
import graphs.compiler as _compiler


# ─── Fixture: aislamiento del cooldown entre tests ───────────────────────────

@pytest.fixture(autouse=True)
def reset_cooldown():
    """Limpia el dict de cooldown antes de cada test para evitar contaminación."""
    _compiler._flow_cooldown.clear()
    yield
    _compiler._flow_cooldown.clear()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _state_with_ts(hours_old: float | None, connection_id="5491171876959") -> FlowState:
    ts = None if hours_old is None else datetime.now() - timedelta(hours=hours_old)
    return FlowState(
        message="Hola",
        contact_phone="5491199990000",
        canal="whatsapp",
        connection_id=connection_id,
        timestamp=ts,
    )


def _send_node(max_age: float = 1.0) -> SendMessageNode:
    return SendMessageNode({"message": "Respuesta automática", "max_age_hours": max_age})


def _flow_with_send(connection_id: str, max_age: float = 1.0) -> dict:
    """Flow mínimo: trigger → send_message con max_age configurable."""
    return {
        "id": "test-flow-safety",
        "name": "Test flow",
        "connection_id": connection_id,
        "contact_phone": None,
        "created_at": "2020-01-01 00:00:00",
        "definition": {
            "nodes": [
                {"id": "t", "type": "message_trigger",
                 "config": {"connection_id": connection_id}},
                {"id": "s", "type": "send_message",
                 "config": {"message": "Respuesta automática", "max_age_hours": max_age}},
            ],
            "edges": [{"id": "e1", "source": "t", "target": "s", "label": None}],
        },
    }


# ─── 1. max_age_hours — tests directos sobre el nodo ─────────────────────────

@pytest.mark.asyncio
async def test_max_age_bloquea_mensaje_viejo():
    """Mensaje de 2h con límite 1h → reply bloqueado."""
    node = _send_node(max_age=1.0)
    state = _state_with_ts(hours_old=2.0)
    result = await node.run(state)
    assert result.reply is None, "Mensaje de 2h debe ser bloqueado (límite 1h)"


@pytest.mark.asyncio
async def test_max_age_permite_mensaje_reciente():
    """Mensaje de 10 minutos con límite 1h → reply permitido."""
    node = _send_node(max_age=1.0)
    state = _state_with_ts(hours_old=10 / 60)
    result = await node.run(state)
    assert result.reply == "Respuesta automática", "Mensaje de 10min debe pasar"


@pytest.mark.asyncio
async def test_max_age_sin_timestamp_permite():
    """Sin timestamp en state → no bloquear (mensajes live sin info de tiempo)."""
    node = _send_node(max_age=1.0)
    state = _state_with_ts(hours_old=None)
    result = await node.run(state)
    assert result.reply == "Respuesta automática", "Sin timestamp debe pasar siempre"


@pytest.mark.asyncio
async def test_max_age_cero_desactiva_limite():
    """max_age_hours=0 → sin límite, siempre pasa aunque el mensaje sea muy viejo."""
    node = _send_node(max_age=0)
    state = _state_with_ts(hours_old=48.0)   # 2 días
    result = await node.run(state)
    assert result.reply == "Respuesta automática", "max_age=0 debe desactivar el límite"


@pytest.mark.asyncio
async def test_from_delta_sync_siempre_bloqueado():
    """from_delta_sync=True → reply bloqueado independiente de max_age."""
    node = _send_node(max_age=0)  # incluso con max_age desactivado
    state = _state_with_ts(hours_old=0.1)
    state.from_delta_sync = True
    result = await node.run(state)
    assert result.reply is None, "from_delta_sync siempre debe bloquear el reply"


@pytest.mark.asyncio
async def test_max_age_en_to_explicito_no_aplica():
    """Cuando 'to' tiene destinatario explícito, max_age no aplica (no es reply al usuario)."""
    node = SendMessageNode({
        "to": "5491199990000",
        "message": "Notificación al trabajador",
        "max_age_hours": 0.001,   # límite casi cero
    })
    state = _state_with_ts(hours_old=1.0)

    # _send() fallará porque no hay WA/TG real, pero el check de age no debe intervenir.
    # Reemplazamos _send para que no falle el test por ausencia de bot.
    node._send = AsyncMock()
    result = await node.run(state)
    node._send.assert_called_once()   # llegó a _send (no fue bloqueado antes)


# ─── helpers de cooldown ─────────────────────────────────────────────────────

def _tg_flow_with_cooldown(connection_id: str, cooldown_hours: float = 4.0, include_cooldown_key: bool = True) -> dict:
    """Flow con telegram_trigger y cooldown configurable."""
    trigger_config = {"connection_id": connection_id, "message_pattern": ""}
    if include_cooldown_key:
        trigger_config["cooldown_hours"] = cooldown_hours
    return {
        "id": "test-tg-cooldown",
        "name": "Test TG cooldown",
        "connection_id": connection_id,
        "contact_phone": None,
        "created_at": "2020-01-01 00:00:00",
        "definition": {
            "nodes": [
                {"id": "t", "type": "telegram_trigger", "config": trigger_config},
                {"id": "s", "type": "send_message",
                 "config": {"message": "Hola desde TG", "max_age_hours": 0}},
            ],
            "edges": [{"id": "e1", "source": "t", "target": "s", "label": None}],
        },
    }


def _tg_state(contact_phone: str, connection_id: str) -> FlowState:
    return FlowState(
        message="Hola",
        contact_phone=contact_phone,
        canal="telegram",
        connection_id=connection_id,
    )


ENV_PATCHES = {
    "DISABLE_AUTO_REPLY": "false",
    "DISABLE_AUTO_REPLY_PHONES": "",
}

CONFIG_MOCK = {"empresas": [{"id": "empresa_test", "name": "Test"}]}


# ─── 2. Cooldown (telegram_trigger) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_cooldown_tg_primer_mensaje_pasa():
    """Primer mensaje de un contacto → reply pasa y cooldown se registra."""
    bot_id = "empresa_test-tg-12345"
    contact = "9876543"
    flow = _tg_flow_with_cooldown(bot_id, cooldown_hours=4.0)
    state = _tg_state(contact, bot_id)

    # Limpiar cooldown para que el test sea aislado
    _compiler._flow_cooldown.clear()

    with patch.dict(os.environ, ENV_PATCHES), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value=CONFIG_MOCK), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=False):
        result = await run_flows(state, connection_id=bot_id)

    assert result.reply == "Hola desde TG", "Primer mensaje debe pasar"
    assert ("test-tg-cooldown", contact) in _compiler._flow_cooldown, "Cooldown debe quedar registrado"


@pytest.mark.asyncio
async def test_cooldown_tg_segundo_mensaje_bloqueado():
    """Segundo mensaje dentro del cooldown → reply bloqueado."""
    import time
    bot_id = "empresa_test-tg-12345"
    contact = "9876543"
    flow = _tg_flow_with_cooldown(bot_id, cooldown_hours=4.0)

    # Simular que ya respondimos hace 30 segundos (dentro del cooldown de 4h)
    _compiler._flow_cooldown[("test-tg-cooldown", contact)] = time.time() - 30

    state = _tg_state(contact, bot_id)

    with patch.dict(os.environ, ENV_PATCHES), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value=CONFIG_MOCK), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=False):
        result = await run_flows(state, connection_id=bot_id)

    assert result.reply is None, "Mensaje dentro del cooldown debe ser bloqueado"


@pytest.mark.asyncio
async def test_cooldown_tg_otro_contacto_no_afectado():
    """Cooldown de un contacto no bloquea a otro contacto distinto."""
    import time
    bot_id = "empresa_test-tg-12345"
    contact_a = "111111"
    contact_b = "222222"
    flow = _tg_flow_with_cooldown(bot_id, cooldown_hours=4.0)

    # Solo contact_a tiene cooldown activo
    _compiler._flow_cooldown[("test-tg-cooldown", contact_a)] = time.time() - 30
    _compiler._flow_cooldown.pop(("test-tg-cooldown", contact_b), None)

    state_b = _tg_state(contact_b, bot_id)

    with patch.dict(os.environ, ENV_PATCHES), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value=CONFIG_MOCK), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=False):
        result = await run_flows(state_b, connection_id=bot_id)

    assert result.reply == "Hola desde TG", "Contacto distinto no debe estar bloqueado por cooldown ajeno"


@pytest.mark.asyncio
async def test_cooldown_tg_sin_campo_usa_default_schema():
    """
    Flow creado antes de que existiera cooldown_hours (campo ausente en config) →
    el backend usa el default del schema (4h) en lugar de 0.
    Esto evita que flows viejos queden sin cooldown silenciosamente.
    """
    import time
    bot_id = "empresa_test-tg-12345"
    contact = "9876543"
    # Flow sin cooldown_hours en el trigger config (simula flow creado antes del campo)
    flow = _tg_flow_with_cooldown(bot_id, cooldown_hours=0, include_cooldown_key=False)

    # Simular cooldown activo (respuesta enviada hace 30 segundos, dentro del default 4h)
    _compiler._flow_cooldown[("test-tg-cooldown", contact)] = time.time() - 30

    state = _tg_state(contact, bot_id)

    with patch.dict(os.environ, ENV_PATCHES), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value=CONFIG_MOCK), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=False):
        result = await run_flows(state, connection_id=bot_id)

    assert result.reply is None, "Sin cooldown_hours en config → usa default 4h → bloqueado dentro del cooldown"


# ─── 3. max_age en run_flows (integración con mocks) ─────────────────────────

@pytest.mark.asyncio
async def test_run_flows_bloquea_mensaje_viejo():
    """run_flows con mensaje viejo → reply None aunque el flow produzca uno."""
    bot_id = "5491171876959"
    flow = _flow_with_send(bot_id, max_age=1.0)
    state = _state_with_ts(hours_old=3.0, connection_id=bot_id)

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "empresa_test", "name": "Test"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=False):
        result = await run_flows(state, connection_id=bot_id)

    assert result.reply is None, "Mensaje de 3h debe ser bloqueado en run_flows"


@pytest.mark.asyncio
async def test_run_flows_permite_mensaje_reciente():
    """run_flows con mensaje reciente → reply pasa."""
    bot_id = "5491171876959"
    flow = _flow_with_send(bot_id, max_age=1.0)
    state = _state_with_ts(hours_old=0.1, connection_id=bot_id)

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "empresa_test", "name": "Test"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=False):
        result = await run_flows(state, connection_id=bot_id)

    assert result.reply == "Respuesta automática", "Mensaje reciente debe pasar en run_flows"


# ─── 3. Pausa por empresa ─────────────────────────────────────────────────────

def test_pause_sets_is_paused(tmp_path):
    """pause() hace que is_paused() retorne True."""
    import paused
    original_file = paused._FILE
    paused._FILE = tmp_path / "paused_bots.json"
    paused._paused = set()
    try:
        assert not paused.is_paused("empresa_x")
        paused.pause("empresa_x")
        assert paused.is_paused("empresa_x")
    finally:
        paused._FILE = original_file
        paused._paused = set()


def test_resume_clears_is_paused(tmp_path):
    """resume() hace que is_paused() retorne False."""
    import paused
    original_file = paused._FILE
    paused._FILE = tmp_path / "paused_bots.json"
    paused._paused = {"empresa_x"}
    try:
        assert paused.is_paused("empresa_x")
        paused.resume("empresa_x")
        assert not paused.is_paused("empresa_x")
    finally:
        paused._FILE = original_file
        paused._paused = set()


def test_pause_persiste_en_disco(tmp_path):
    """pause() escribe en disco; _load() lo recupera."""
    import paused, json
    paused._FILE = tmp_path / "paused_bots.json"
    paused._paused = set()
    paused.pause("empresa_y")

    data = json.loads(paused._FILE.read_text())
    assert "empresa_y" in data["paused"]

    # Simular reinicio
    paused._paused = set()
    paused._load()
    assert paused.is_paused("empresa_y")

    # Cleanup
    paused._paused = set()


@pytest.mark.asyncio
async def test_run_flows_empresa_pausada_no_responde():
    """Empresa pausada → run_flows retorna reply=None."""
    bot_id = "5491171876959"
    flow = _flow_with_send(bot_id, max_age=0)  # sin límite de edad
    state = _state_with_ts(hours_old=None, connection_id=bot_id)

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "empresa_test", "name": "Test"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=True):
        result = await run_flows(state, connection_id=bot_id)

    assert result.reply is None, "Empresa pausada debe retornar reply=None"


@pytest.mark.asyncio
async def test_run_flows_empresa_reanudada_responde():
    """Empresa NO pausada → reply pasa normalmente."""
    bot_id = "5491171876959"
    flow = _flow_with_send(bot_id, max_age=0)
    state = _state_with_ts(hours_old=None, connection_id=bot_id)

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_connection", return_value=["empresa_test"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "empresa_test", "name": "Test"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]), \
         patch("paused.is_paused", return_value=False):
        result = await run_flows(state, connection_id=bot_id)

    assert result.reply == "Respuesta automática", "Empresa activa debe responder"
