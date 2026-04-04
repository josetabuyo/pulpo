"""
Tests de seguridad del motor de flows.

Garantizan que el sistema NO envía mensajes cuando no debe:

  1. connection_id NULL en un flow → nunca dispara para nadie
  2. connection_id correcto → sí dispara
  3. DISABLE_AUTO_REPLY=true → reply descartado globalmente
  4. DISABLE_AUTO_REPLY_PHONES → reply descartado solo para ese número
  5. Guard activated_at → no responde mensajes anteriores al flow

Son tests unitarios puros — no requieren servidor corriendo.
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from graphs.compiler import run_flows
from graphs.nodes.state import FlowState


# ─── Fixture: flow con ReplyNode ────────────────────────────────────────────

def _flow(connection_id=None, contact_phone=None, message="Hola Test"):
    """Flow mínimo con un ReplyNode configurado."""
    return {
        "id": "test-flow-id",
        "name": "Flow de prueba",
        "connection_id": connection_id,
        "contact_phone": contact_phone,
        "created_at": "2020-01-01 00:00:00",   # muy viejo: siempre pasa el guard de timestamp
        "definition": {
            "nodes": [
                {"id": "__start__",  "type": "start", "config": {}},
                {"id": "reply_node", "type": "reply", "config": {"message": message}},
                {"id": "__end__",    "type": "end",   "config": {}},
            ],
            "edges": [],
        },
    }

def _state(bot_id="5491155612767"):
    return FlowState(
        message="Hola",
        contact_phone="5491199990000",
        canal="whatsapp",
    )


# ─── 1. connection_id NULL nunca dispara ───────────────────────���────────────

@pytest.mark.asyncio
async def test_flow_sin_connection_no_dispara():
    """
    Un flow con connection_id=NULL no debe ser retornado por la DB.
    La garantía real está en test_db_connection_null_no_retorna_flow (DB directa).
    Este test verifica que si por algún bug la DB lo devuelve igual,
    el reply no queda bloqueado en el engine (el engine confía en que DB ya filtró,
    así que si llega un flow lo ejecuta — el filtro debe estar en la DB).
    """
    import db as db_module
    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_null_engine__",
        definition={"nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {"id": "r", "type": "reply", "config": {"message": "no debe llegar"}},
            {"id": "__end__", "type": "end", "config": {}},
        ], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id=None,   # NULL — no debe ser retornado por get_active_flows_for_bot
    )
    try:
        flows = await db_module.get_active_flows_for_bot(
            bot_id="5491155612767", contact_phone="5491199990000", empresa_id="bot_test"
        )
        assert flow_id not in [f["id"] for f in flows], \
            "Flow con connection_id=NULL no debe disparar para ningún número."
    finally:
        await db_module.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_flow_con_connection_correcta_dispara():
    """Un flow con connection_id correcto sí debe ser retornado por la DB."""
    import db as db_module
    bot_id = "5491171876959"
    flow_id = await db_module.create_flow(
        empresa_id="gm_herreria",
        name="__test_connection_correcta__",
        definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id=bot_id,
    )
    try:
        flows = await db_module.get_active_flows_for_bot(
            bot_id=bot_id, contact_phone="5491199990000", empresa_id="gm_herreria"
        )
        assert flow_id in [f["id"] for f in flows], \
            "Flow con connection_id correcto debe ser retornado."
    finally:
        await db_module.delete_flow(flow_id)


# ─── 2. DB: connection_id NULL no retorna el flow ───────────────────────────

@pytest.mark.asyncio
async def test_db_connection_null_no_retorna_flow():
    """
    get_active_flows_for_bot con connection_id=NULL no debe retornar el flow.
    El NULL no es wildcard — la conexión debe ser explícita.
    """
    import db as db_module

    # Crear un flow con connection_id NULL en la DB de test
    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__safety_test_null_connection__",
        definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id=None,
        contact_phone=None,
    )

    try:
        # Consultar como si llegara un mensaje al número 5491155612767
        flows = await db_module.get_active_flows_for_bot(
            bot_id="5491155612767",
            contact_phone="5491199990000",
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_id not in ids, (
            "PELIGRO: flow con connection_id=NULL fue devuelto por get_active_flows_for_bot. "
            "Esto significa que respondería a TODOS los contactos de TODOS los números."
        )
    finally:
        await db_module.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_db_connection_correcta_retorna_flow():
    """Un flow con connection_id correcto sí debe ser retornado."""
    import db as db_module

    bot_id = "5491155612767"
    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__safety_test_con_connection__",
        definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id=bot_id,
        contact_phone=None,
    )

    try:
        flows = await db_module.get_active_flows_for_bot(
            bot_id=bot_id,
            contact_phone="5491199990000",
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_id in ids, "El flow con connection_id correcto debería ser retornado."
    finally:
        await db_module.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_db_connection_distinta_no_retorna_flow():
    """Un flow asignado a otro número no debe disparar para el número incorrecto."""
    import db as db_module

    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__safety_test_otro_numero__",
        definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id="5491171876959",   # número de GM herrería
        contact_phone=None,
    )

    try:
        # Llega un mensaje al 67 (número personal) — no debe ver este flow
        flows = await db_module.get_active_flows_for_bot(
            bot_id="5491155612767",
            contact_phone="5491199990000",
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_id not in ids, "Un flow de otro número no debe disparar para este número."
    finally:
        await db_module.delete_flow(flow_id)


# ─── 3. Kill switch global DISABLE_AUTO_REPLY ───────────────────────────────

@pytest.mark.asyncio
async def test_kill_switch_global_descarta_reply():
    """DISABLE_AUTO_REPLY=true debe descartar el reply aunque el flow produzca uno."""
    bot_id = "5491171876959"
    flow = _flow(connection_id=bot_id, message="Este mensaje NO debe llegar")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "true", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_bot", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"bots": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(bot_id), bot_id=bot_id)

    assert state.reply is None, "DISABLE_AUTO_REPLY=true debe bloquear el reply."
    assert state.image_url is None


@pytest.mark.asyncio
async def test_kill_switch_global_false_permite_reply():
    """Con DISABLE_AUTO_REPLY=false, el reply debe pasar."""
    bot_id = "5491171876959"
    flow = _flow(connection_id=bot_id, message="Bienvenido")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_bot", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"bots": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(bot_id), bot_id=bot_id)

    assert state.reply == "Bienvenido"


# ─── 4. Kill switch por número DISABLE_AUTO_REPLY_PHONES ────────────────────

@pytest.mark.asyncio
async def test_kill_switch_por_numero_bloquea_ese_numero():
    """El número personal (67) no debe mandar replies aunque tenga un flow activo."""
    blocked = "5491155612767"
    flow = _flow(connection_id=blocked, message="Este NO debe llegar")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": blocked}), \
         patch("config.get_empresas_for_bot", return_value=["bot_test"]), \
         patch("config.load_config", return_value={"bots": [{"id": "bot_test", "name": "Test"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(blocked), bot_id=blocked)

    assert state.reply is None, f"El número {blocked} no debe mandar replies (está en DISABLE_AUTO_REPLY_PHONES)."


@pytest.mark.asyncio
async def test_kill_switch_por_numero_no_afecta_otros():
    """Bloquear el 67 no debe afectar a otros números."""
    blocked  = "5491155612767"
    otro     = "5491171876959"
    flow = _flow(connection_id=otro, message="Respuesta de GM")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": blocked}), \
         patch("config.get_empresas_for_bot", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"bots": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(otro), bot_id=otro)

    assert state.reply == "Respuesta de GM", "El número 59 no debe verse afectado por el bloqueo del 67."


# ─── 5. Guard activated_at: no responder mensajes anteriores al flow ─────────

@pytest.mark.asyncio
async def test_guard_activatedat_bloquea_mensaje_viejo():
    """Un mensaje anterior a la creación del flow no debe recibir respuesta."""
    bot_id = "5491171876959"
    flow = _flow(connection_id=bot_id, message="No debería enviarse")
    flow["created_at"] = "2026-04-04 12:00:00"   # flow creado hoy a las 12

    state = _state(bot_id)
    state.timestamp = datetime(2026, 4, 3, 10, 0, 0)   # mensaje de ayer

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_bot", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"bots": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(state, bot_id=bot_id)

    assert state.reply is None, "Mensaje anterior al flow no debe recibir respuesta (guard activated_at)."


@pytest.mark.asyncio
async def test_guard_activatedat_permite_mensaje_nuevo():
    """Un mensaje posterior a la creación del flow sí debe recibir respuesta."""
    bot_id = "5491171876959"
    flow = _flow(connection_id=bot_id, message="Bienvenido")
    flow["created_at"] = "2026-04-04 12:00:00"   # flow creado a las 12

    state = _state(bot_id)
    state.timestamp = datetime(2026, 4, 4, 13, 0, 0)   # mensaje posterior

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_bot", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"bots": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(state, bot_id=bot_id)

    assert state.reply == "Bienvenido"
