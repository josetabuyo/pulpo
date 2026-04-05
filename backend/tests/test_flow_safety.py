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
    config = {}
    if connection_id:
        config["connection_id"] = connection_id
    if contact_phone:
        config["contact_phone"] = contact_phone

    return {
        "id": "test-flow-id",
        "name": "Flow de prueba",
        "connection_id": connection_id,
        "contact_phone": contact_phone,
        "created_at": "2020-01-01 00:00:00",   # muy viejo: siempre pasa el guard de timestamp
        "definition": {
            "nodes": [
                {"id": "trigger_node", "type": "message_trigger", "config": config},
                {"id": "reply_node", "type": "reply", "config": {"message": message}},
            ],
            "edges": [
                {"id": "e1", "source": "trigger_node", "target": "reply_node", "label": None},
            ],
        },
    }

def _state(connection_id="5491155612767"):
    return FlowState(
        message="Hola",
        contact_phone="5491199990000",
        canal="whatsapp",
        connection_id=connection_id,
    )


# ─── 1. connection_id NULL nunca dispara ───────────────────────���────────────

@pytest.mark.asyncio
async def test_create_flow_sin_connection_id_rechazado():
    """
    create_flow con connection_id=None debe lanzar ValueError.
    No se puede crear un flow sin conexión — es el primer guard de seguridad.
    """
    import db as db_module
    with pytest.raises(ValueError, match="connection_id"):
        await db_module.create_flow(
            empresa_id="bot_test",
            name="__test_null_engine__",
            definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
            connection_id=None,
        )


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
async def test_db_connection_null_rechazado_en_create():
    """
    connection_id=NULL ya no puede insertarse — create_flow levanta ValueError antes.
    Este test documenta la garantía: no existe ruta para crear un flow sin conexión.
    """
    import db as db_module

    with pytest.raises(ValueError, match="connection_id"):
        await db_module.create_flow(
            empresa_id="bot_test",
            name="__safety_test_null_connection__",
            definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
            connection_id=None,
            contact_phone=None,
        )


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


@pytest.mark.asyncio
async def test_flow_con_message_trigger_y_connection_null_en_db():
    """
    Flow con connection_id explícito en DB y nodo message_trigger que especifica el mismo connection_id.
    Debe ejecutarse correctamente.
    """
    import db as db_module

    bot_id = "5491155612767"
    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_message_trigger_con_connection__",
        definition={
            "nodes": [
                {"id": "input1", "type": "message_trigger", "config": {"connection_id": bot_id}},
                {"id": "reply1", "type": "reply", "config": {"message": "Mensaje desde message_trigger"}},
            ],
            "edges": [
                {"id": "e1", "source": "input1", "target": "reply1", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        },
        connection_id=bot_id,  # DEBE tener connection_id explícito para ser retornado por la DB
        contact_phone=None,
    )

    try:
        # Debe ser retornado por la DB
        flows = await db_module.get_active_flows_for_bot(
            bot_id=bot_id,
            contact_phone="5491199990000",
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_id in ids, "Flow con connection_id explícito debe ser retornado por la DB"

        # Debe ejecutarse correctamente
        from graphs.compiler import execute_flow
        from graphs.nodes.state import FlowState

        flow = next(f for f in flows if f["id"] == flow_id)
        state = FlowState(
            message="Hola",
            contact_phone="5491199990000",
            canal="whatsapp",
            connection_id=bot_id,
        )
        state = await execute_flow(flow, state)
        assert state.reply == "Mensaje desde message_trigger", "Flow con message_trigger y connection_id correcto debe ejecutarse"
    finally:
        await db_module.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_flow_con_message_trigger_wrong_connection():
    """
    Flow con connection_id explícito pero incorrecto en DB.
    No debe ser retornado por la DB.
    """
    import db as db_module

    wrong_bot_id = "5491171876959"  # GM herrería
    actual_bot_id = "5491155612767"  # Número personal
    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_message_trigger_wrong_connection__",
        definition={
            "nodes": [
                {"id": "input1", "type": "message_trigger", "config": {"connection_id": wrong_bot_id}},
                {"id": "reply1", "type": "reply", "config": {"message": "No debe llegar"}},
            ],
            "edges": [
                {"id": "e1", "source": "input1", "target": "reply1", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        },
        connection_id=wrong_bot_id,  # connection_id explícito pero incorrecto
        contact_phone=None,
    )

    try:
        # La DB NO debe retornarlo (connection_id incorrecto)
        flows = await db_module.get_active_flows_for_bot(
            bot_id=actual_bot_id,
            contact_phone="5491199990000",
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]

        assert flow_id not in ids, "Flow con connection_id incorrecto no debe ser retornado por la DB"
    finally:
        await db_module.delete_flow(flow_id)


# ─── Tests para InputTextNode ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_trigger_filtra_por_contact_phone():
    """InputTextNode debe filtrar por contact_phone cuando está especificado."""
    import db as db_module

    bot_id = "5491155612767"
    correct_contact = "5491199990000"
    wrong_contact = "5491199991111"

    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_message_trigger_contact_phone__",
        definition={
            "nodes": [
                {"id": "input1", "type": "message_trigger", "config": {"connection_id": bot_id, "contact_phone": correct_contact}},
                {"id": "reply1", "type": "reply", "config": {"message": "Mensaje para contacto específico"}},
            ],
            "edges": [
                {"id": "e1", "source": "input1", "target": "reply1", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        },
        connection_id=bot_id,
        contact_phone=None,
    )

    try:
        # La DB retorna el flow (connection_id correcto)
        flows = await db_module.get_active_flows_for_bot(
            bot_id=bot_id,
            contact_phone=correct_contact,
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_id in ids, "Flow debe ser retornado por la DB"

        # Test 1: Contacto correcto → debe ejecutarse
        from graphs.compiler import execute_flow
        from graphs.nodes.state import FlowState

        flow = next(f for f in flows if f["id"] == flow_id)
        state = FlowState(
            message="Hola",
            contact_phone=correct_contact,
            canal="whatsapp",
            connection_id=bot_id,
        )
        state = await execute_flow(flow, state)
        assert state.reply == "Mensaje para contacto específico", "Flow debe ejecutarse para contacto correcto"

        # Test 2: Contacto incorrecto → NO debe ejecutarse
        state2 = FlowState(
            message="Hola",
            contact_phone=wrong_contact,
            canal="whatsapp",
            connection_id=bot_id,
        )
        state2 = await execute_flow(flow, state2)
        assert state2.reply is None, "Flow NO debe ejecutarse para contacto incorrecto"

    finally:
        await db_module.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_message_trigger_sin_contact_phone_filtra_todos():
    """InputTextNode sin contact_phone debe ejecutarse para cualquier contacto."""
    import db as db_module

    bot_id = "5491155612767"
    contact1 = "5491199990000"
    contact2 = "5491199991111"

    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_message_trigger_sin_contact__",
        definition={
            "nodes": [
                {"id": "input1", "type": "message_trigger", "config": {"connection_id": bot_id}},
                {"id": "reply1", "type": "reply", "config": {"message": "Mensaje para todos"}},
            ],
            "edges": [
                {"id": "e1", "source": "input1", "target": "reply1", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        },
        connection_id=bot_id,
        contact_phone=None,
    )

    try:
        # La DB retorna el flow
        flows = await db_module.get_active_flows_for_bot(
            bot_id=bot_id,
            contact_phone=contact1,
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_id in ids, "Flow debe ser retornado por la DB"

        # Test 1: Contacto 1 → debe ejecutarse
        from graphs.compiler import execute_flow
        from graphs.nodes.state import FlowState

        flow = next(f for f in flows if f["id"] == flow_id)
        state = FlowState(
            message="Hola",
            contact_phone=contact1,
            canal="whatsapp",
            connection_id=bot_id,
        )
        state = await execute_flow(flow, state)
        assert state.reply == "Mensaje para todos", "Flow debe ejecutarse para contacto 1"

        # Test 2: Contacto 2 → también debe ejecutarse
        state2 = FlowState(
            message="Hola",
            contact_phone=contact2,
            canal="whatsapp",
            connection_id=bot_id,
        )
        state2 = await execute_flow(flow, state2)
        assert state2.reply == "Mensaje para todos", "Flow debe ejecutarse para contacto 2 (sin filtro contact_phone)"

    finally:
        await db_module.delete_flow(flow_id)




@pytest.mark.asyncio
async def test_migracion_start_a_message_trigger_explicito():
    """
    Demuestra cómo migrar un flow legacy con __start__ a la nueva forma explícita con InputTextNode.

    El sistema ya NO soporta __start__ como nodo de entrada. Los flows existentes deben ser
    migrados explícitamente para usar InputTextNode con connection_id y contact_phone.
    """
    import db as db_module

    bot_id = "5491155612767"
    contact_phone = "5491199990000"

    # Flow legacy con __start__ (forma vieja)
    flow_legacy_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_migracion_legacy__",
        definition={
            "nodes": [
                {"id": "__start__", "type": "start", "config": {}},
                {"id": "reply1", "type": "reply", "config": {"message": "Mensaje legacy"}},
            ],
            "edges": [
                {"id": "e1", "source": "__start__", "target": "reply1", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        },
        connection_id=bot_id,
        contact_phone=contact_phone,  # contact_phone en DB
    )

    # Flow migrado con InputTextNode (forma nueva explícita)
    flow_migrado_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_migracion_nuevo__",
        definition={
            "nodes": [
                {"id": "input1", "type": "message_trigger", "config": {"connection_id": bot_id, "contact_phone": contact_phone}},
                {"id": "reply1", "type": "reply", "config": {"message": "Mensaje migrado"}},
            ],
            "edges": [
                {"id": "e1", "source": "input1", "target": "reply1", "label": None},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        },
        connection_id=bot_id,
        contact_phone=None,  # contact_phone ahora está en el nodo message_trigger
    )

    try:
        # Ambos flows deben ser retornados por la DB
        flows = await db_module.get_active_flows_for_bot(
            bot_id=bot_id,
            contact_phone=contact_phone,
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_legacy_id in ids, "Flow legacy debe ser retornado"
        assert flow_migrado_id in ids, "Flow migrado debe ser retornado"

        from graphs.compiler import execute_flow
        from graphs.nodes.state import FlowState

        # Test 1: Flow legacy con __start__ SÍ funciona (compatibilidad hacia atrás mantenida)
        flow_legacy = next(f for f in flows if f["id"] == flow_legacy_id)
        state_legacy = FlowState(
            message="Hola",
            contact_phone=contact_phone,
            canal="whatsapp",
            connection_id=bot_id,
        )
        state_legacy = await execute_flow(flow_legacy, state_legacy)
        assert state_legacy.reply == "Mensaje legacy", "Flow legacy con __start__ debe funcionar (compatibilidad hacia atrás)"

        # Test 2: Flow migrado funciona (forma nueva explícita)
        flow_migrado = next(f for f in flows if f["id"] == flow_migrado_id)
        state_migrado = FlowState(
            message="Hola",
            contact_phone=contact_phone,
            canal="whatsapp",
            connection_id=bot_id,
        )
        state_migrado = await execute_flow(flow_migrado, state_migrado)
        assert state_migrado.reply == "Mensaje migrado", "Flow migrado debe funcionar"

        # Test 3: Ventaja de la forma nueva - filtrado más granular
        # Con InputTextNode podemos tener múltiples flows con diferentes contact_phones
        # sin necesidad de duplicar flows en la DB
        flow_migrado_otro_contacto_id = await db_module.create_flow(
            empresa_id="bot_test",
            name="__test_migracion_otro_contacto__",
            definition={
                "nodes": [
                    {"id": "input1", "type": "message_trigger", "config": {"connection_id": bot_id, "contact_phone": "5491199991111"}},
                    {"id": "reply1", "type": "reply", "config": {"message": "Mensaje para otro contacto"}},
                ],
                "edges": [
                    {"id": "e1", "source": "input1", "target": "reply1", "label": None},
                ],
                "viewport": {"x": 0, "y": 0, "zoom": 1}
            },
            connection_id=bot_id,
            contact_phone=None,
        )

        try:
            flows2 = await db_module.get_active_flows_for_bot(
                bot_id=bot_id,
                contact_phone=contact_phone,  # contacto original
                empresa_id="bot_test",
            )

            flow_migrado_otro = next(f for f in flows2 if f["id"] == flow_migrado_otro_contacto_id)
            state_otro = FlowState(
                message="Hola",
                contact_phone=contact_phone,  # contacto original
                canal="whatsapp",
                connection_id=bot_id,
            )
            state_otro = await execute_flow(flow_migrado_otro, state_otro)
            assert state_otro.reply is None, "Flow con contact_phone diferente no debe ejecutarse"

            # Pero sí debe ejecutarse para el contacto correcto
            state_contacto_correcto = FlowState(
                message="Hola",
                contact_phone="5491199991111",  # contacto especificado en el nodo
                canal="whatsapp",
                connection_id=bot_id,
            )
            state_contacto_correcto = await execute_flow(flow_migrado_otro, state_contacto_correcto)
            assert state_contacto_correcto.reply == "Mensaje para otro contacto", "Flow debe ejecutarse para contacto correcto"

        finally:
            await db_module.delete_flow(flow_migrado_otro_contacto_id)

        # Test 4: La forma nueva permite flows sin contact_phone (wildcard)
        flow_migrado_wildcard_id = await db_module.create_flow(
            empresa_id="bot_test",
            name="__test_migracion_wildcard__",
            definition={
                "nodes": [
                    {"id": "input1", "type": "message_trigger", "config": {"connection_id": bot_id}},
                    {"id": "reply1", "type": "reply", "config": {"message": "Mensaje para todos"}},
                ],
                "edges": [
                    {"id": "e1", "source": "input1", "target": "reply1", "label": None},
                ],
                "viewport": {"x": 0, "y": 0, "zoom": 1}
            },
            connection_id=bot_id,
            contact_phone=None,
        )

        try:
            # Debe ejecutarse para cualquier contacto
            flows3 = await db_module.get_active_flows_for_bot(
                bot_id=bot_id,
                contact_phone="5491199999999",  # contacto cualquiera
                empresa_id="bot_test",
            )

            flow_wildcard = next(f for f in flows3 if f["id"] == flow_migrado_wildcard_id)
            state_wildcard = FlowState(
                message="Hola",
                contact_phone="5491199999999",  # contacto cualquiera
                canal="whatsapp",
                connection_id=bot_id,
            )
            state_wildcard = await execute_flow(flow_wildcard, state_wildcard)
            assert state_wildcard.reply == "Mensaje para todos", "Flow wildcard debe ejecutarse para cualquier contacto"

        finally:
            await db_module.delete_flow(flow_migrado_wildcard_id)

    finally:
        await db_module.delete_flow(flow_legacy_id)
        await db_module.delete_flow(flow_migrado_id)


@pytest.mark.asyncio
async def test_flow_sin_nodo_entrada_no_se_ejecuta():
    """Flow sin message_trigger debe ser ignorado."""
    import db as db_module

    bot_id = "5491155612767"
    contact_phone = "5491199990000"

    flow_id = await db_module.create_flow(
        empresa_id="bot_test",
        name="__test_sin_nodo_entrada__",
        definition={
            "nodes": [
                {"id": "reply1", "type": "reply", "config": {"message": "No debe ejecutarse"}},
            ],
            "edges": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        },
        connection_id=bot_id,
        contact_phone=None,
    )

    try:
        # La DB retorna el flow
        flows = await db_module.get_active_flows_for_bot(
            bot_id=bot_id,
            contact_phone=contact_phone,
            empresa_id="bot_test",
        )
        ids = [f["id"] for f in flows]
        assert flow_id in ids, "Flow debe ser retornado por la DB"

        # El engine debe ignorarlo (no hay nodo de entrada)
        from graphs.compiler import execute_flow
        from graphs.nodes.state import FlowState

        flow = next(f for f in flows if f["id"] == flow_id)
        state = FlowState(
            message="Hola",
            contact_phone=contact_phone,
            canal="whatsapp",
            connection_id=bot_id,
        )
        state = await execute_flow(flow, state)
        assert state.reply is None, "Flow sin nodo de entrada debe ser ignorado"

    finally:
        await db_module.delete_flow(flow_id)


# ─── 3. Kill switch global DISABLE_AUTO_REPLY ───────────────────────────────

@pytest.mark.asyncio
async def test_kill_switch_global_descarta_reply():
    """DISABLE_AUTO_REPLY=true debe descartar el reply aunque el flow produzca uno."""
    bot_id = "5491171876959"
    flow = _flow(connection_id=bot_id, message="Este mensaje NO debe llegar")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "true", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_connection", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(bot_id), connection_id=bot_id)

    assert state.reply is None, "DISABLE_AUTO_REPLY=true debe bloquear el reply."
    assert state.image_url is None


@pytest.mark.asyncio
async def test_kill_switch_global_false_permite_reply():
    """Con DISABLE_AUTO_REPLY=false, el reply debe pasar."""
    bot_id = "5491171876959"
    flow = _flow(connection_id=bot_id, message="Bienvenido")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": ""}), \
         patch("config.get_empresas_for_connection", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(bot_id), connection_id=bot_id)

    assert state.reply == "Bienvenido"


# ─── 4. Kill switch por número DISABLE_AUTO_REPLY_PHONES ────────────────────

@pytest.mark.asyncio
async def test_kill_switch_por_numero_bloquea_ese_numero():
    """El número personal (67) no debe mandar replies aunque tenga un flow activo."""
    blocked = "5491155612767"
    flow = _flow(connection_id=blocked, message="Este NO debe llegar")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": blocked}), \
         patch("config.get_empresas_for_connection", return_value=["bot_test"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "bot_test", "name": "Test"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(blocked), connection_id=blocked)

    assert state.reply is None, f"El número {blocked} no debe mandar replies (está en DISABLE_AUTO_REPLY_PHONES)."


@pytest.mark.asyncio
async def test_kill_switch_por_numero_no_afecta_otros():
    """Bloquear el 67 no debe afectar a otros números."""
    blocked  = "5491155612767"
    otro     = "5491171876959"
    flow = _flow(connection_id=otro, message="Respuesta de GM")

    with patch.dict(os.environ, {"DISABLE_AUTO_REPLY": "false", "DISABLE_AUTO_REPLY_PHONES": blocked}), \
         patch("config.get_empresas_for_connection", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(_state(otro), connection_id=otro)

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
         patch("config.get_empresas_for_connection", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(state, connection_id=bot_id)

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
         patch("config.get_empresas_for_connection", return_value=["gm_herreria"]), \
         patch("config.load_config", return_value={"empresas": [{"id": "gm_herreria", "name": "GM"}]}), \
         patch("graphs.compiler.resolve_flows", new_callable=AsyncMock, return_value=[flow]):

        state = await run_flows(state, connection_id=bot_id)

    assert state.reply == "Bienvenido"
