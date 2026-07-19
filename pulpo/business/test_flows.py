"""Tests unitarios de duplicate_flow (usa la DB sqlite del worktree directamente)."""
import pytest

from pulpo.core import db
from pulpo.business import flows as svc

BOT_ID = "__test_bot_duplicate_flow__"


@pytest.fixture(autouse=True)
async def _init_db():
    await db.init_db()


async def _cleanup(*flow_ids):
    for flow_id in flow_ids:
        await db.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_duplicate_flow_copies_fields_and_starts_inactive():
    original = await svc.create_flow(
        bot_id=BOT_ID,
        name="Original",
        definition={"nodes": [{"id": "n1", "type": "reply"}], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id="conn-1",
        contact_phone="5491100000000",
        contact_filter={"tag": "vip"},
    )
    try:
        duplicate = await svc.duplicate_flow(BOT_ID, original["id"], "Original (copia)")
        try:
            assert duplicate["name"] == "Original (copia)"
            assert duplicate["id"] != original["id"]
            assert duplicate["definition"] == original["definition"]
            assert duplicate["connection_id"] == original["connection_id"]
            assert duplicate["contact_phone"] == original["contact_phone"]
            assert duplicate["contact_filter"] == original["contact_filter"]
            assert duplicate["active"] is False
            # El original no se toca
            still_there = await svc.get_flow(original["id"], BOT_ID)
            assert still_there["active"] is True
        finally:
            await _cleanup(duplicate["id"])
    finally:
        await _cleanup(original["id"])


@pytest.mark.asyncio
async def test_duplicate_flow_raises_if_not_found():
    with pytest.raises(ValueError):
        await svc.duplicate_flow(BOT_ID, "no-existe", "Copia")


@pytest.mark.asyncio
async def test_duplicate_flow_raises_if_owned_by_other_bot():
    original = await svc.create_flow(
        bot_id=BOT_ID,
        name="Original",
        definition=None,
        connection_id=None,
        contact_phone=None,
        contact_filter=None,
    )
    try:
        with pytest.raises(ValueError):
            await svc.duplicate_flow("otro_bot", original["id"], "Copia")
    finally:
        await _cleanup(original["id"])


@pytest.mark.asyncio
async def test_create_flow_seeds_first_version():
    flow = await svc.create_flow(
        bot_id=BOT_ID, name="Con historial", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        versions = await svc.get_flow_versions(BOT_ID, flow["id"])
        assert len(versions) == 1
        assert versions[0]["name"] == "Con historial"
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_update_flow_saves_version_only_when_explicit():
    flow = await svc.create_flow(
        bot_id=BOT_ID, name="V1", definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        # Auto-save (save_version=False) no debe agregar versiones nuevas.
        await svc.update_flow(BOT_ID, flow["id"], {"definition": {"nodes": [{"id": "n1", "type": "reply"}], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}})
        versions = await svc.get_flow_versions(BOT_ID, flow["id"])
        assert len(versions) == 1  # solo la sembrada al crear

        # Guardado explícito sí debe snapshotear el estado previo.
        await svc.update_flow(BOT_ID, flow["id"], {"definition": {"nodes": [{"id": "n2", "type": "reply"}], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}}, save_version=True)
        versions = await svc.get_flow_versions(BOT_ID, flow["id"])
        assert len(versions) == 2

        full = await svc.get_flow_version(BOT_ID, flow["id"], versions[0]["id"])
        assert full["definition"]["nodes"][0]["id"] == "n1"
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_flow_versions_pruned_to_limit():
    flow = await svc.create_flow(
        bot_id=BOT_ID, name="Muchas versiones", definition={"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        for i in range(60):
            await svc.update_flow(
                BOT_ID, flow["id"],
                {"definition": {"nodes": [{"id": f"n{i}", "type": "reply"}], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}},
                save_version=True,
            )
        versions = await svc.get_flow_versions(BOT_ID, flow["id"])
        assert len(versions) == 50
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_get_flow_version_denies_other_bot():
    flow = await svc.create_flow(
        bot_id=BOT_ID, name="Privado", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        versions = await svc.get_flow_versions(BOT_ID, flow["id"])
        assert await svc.get_flow_versions("otro_bot", flow["id"]) is None
        assert await svc.get_flow_version("otro_bot", flow["id"], versions[0]["id"]) is None
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_migrate_fetch_node_types_a_fetch_http():
    definition = {
        "nodes": [
            {"id": "buscar_fb", "type": "fetch", "config": {"source": "facebook", "fb_page_id": "luganense"}},
            {"id": "buscar_dir", "type": "fetch", "config": {"source": "http", "url": "https://x.test/{query}"}},
            {"id": "buscar_default", "type": "fetch", "config": {}},
            {"id": "otro", "type": "llm", "config": {"prompt": "hola"}},
        ],
        "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    flow = await svc.create_flow(
        bot_id=BOT_ID, name="Con nodos fetch viejos", definition=definition,
        connection_id="conn-1", contact_phone=None, contact_filter=None,
    )
    try:
        await svc.migrate_fetch_node_types()
        migrated = await svc.get_flow(flow["id"], BOT_ID)
        by_id = {n["id"]: n for n in migrated["definition"]["nodes"]}

        assert by_id["buscar_fb"]["type"] == "fetch_http"
        assert "source" not in by_id["buscar_fb"]["config"]
        assert by_id["buscar_dir"]["type"] == "fetch_http"
        assert "source" not in by_id["buscar_dir"]["config"]
        assert by_id["buscar_default"]["type"] == "fetch_http"
        assert by_id["otro"]["type"] == "llm"  # no tocado
    finally:
        await _cleanup(flow["id"])


BOT_ID_SIM = "__test_bot_simulate_message__"


@pytest.mark.asyncio
async def test_simulate_message_new_conversation_returns_reply_and_marks_is_sim():
    """
    Igual que un mensaje real: no se especifica flow_id ni trigger_node_id —
    simulate_message los resuelve solo, igual que dispatch_message.
    """
    definition = {
        "nodes": [
            {"id": "trigger1", "type": "telegram_trigger", "config": {}},
            {"id": "reply1", "type": "send_message", "config": {"message": "hola {{contact_name}}"}},
        ],
        "edges": [{"source": "trigger1", "target": "reply1"}],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    flow = await svc.create_flow(
        bot_id=BOT_ID_SIM, name="Simulable", definition=definition,
        connection_id="conn-1", contact_phone=None, contact_filter=None,
    )
    try:
        result = await svc.simulate_message(bot_id=BOT_ID_SIM, message="necesito un plomero")
        assert result["ok"] is True
        assert result["reply"] == "hola Simulación"
        assert result["sim_id"].startswith("sim-")
        assert result["run_id"]

        async with db.AsyncSessionLocal() as session:
            r = (await session.execute(
                db.text("SELECT is_sim FROM flow_runs WHERE run_id = :rid"),
                {"rid": result["run_id"]},
            )).fetchone()
        assert r is not None
        assert r[0] == 1
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_simulate_message_raises_if_bot_has_no_active_message_flow():
    with pytest.raises(ValueError):
        await svc.simulate_message(bot_id="__bot_sin_flows__", message="hola")


@pytest.mark.asyncio
async def test_simulate_message_ignores_inactive_flow():
    """
    A diferencia de un mensaje real, simular no debe "encontrar" un flow
    inactivo — mismo criterio que dispatch_message (resolve_flows solo trae
    flows activos): si la bot no tiene ningún flow activo, simular falla
    igual que fallaría un mensaje real (nadie respondería).
    """
    definition = {
        "nodes": [
            {"id": "trigger1", "type": "telegram_trigger", "config": {}},
            {"id": "reply1", "type": "send_message", "config": {"message": "hola"}},
        ],
        "edges": [{"source": "trigger1", "target": "reply1"}],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    flow = await svc.create_flow(
        bot_id=BOT_ID_SIM, name="Inactivo", definition=definition,
        connection_id="conn-1", contact_phone=None, contact_filter=None,
    )
    try:
        await svc.update_flow(BOT_ID_SIM, flow["id"], {"active": False})
        with pytest.raises(ValueError):
            await svc.simulate_message(bot_id=BOT_ID_SIM, message="hola")
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_simulate_message_forces_sim_prefix_on_caller_supplied_sim_id():
    """
    Un contact_phone real jamás debe poder colarse como identidad de una
    simulación — wait_user/open_conversations indexan por contact_phone sin
    chequear is_sim, así que un sim_id sin namespacear podría contaminar el
    estado de un contacto real.
    """
    definition = {
        "nodes": [
            {"id": "trigger1", "type": "telegram_trigger", "config": {}},
            {"id": "reply1", "type": "send_message", "config": {"message": "hola"}},
        ],
        "edges": [{"source": "trigger1", "target": "reply1"}],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    flow = await svc.create_flow(
        bot_id=BOT_ID_SIM, name="Namespacing", definition=definition,
        connection_id="conn-1", contact_phone=None, contact_filter=None,
    )
    try:
        result = await svc.simulate_message(
            bot_id=BOT_ID_SIM, message="hola", sim_id="6593910266",
        )
        assert result["sim_id"] == "sim-6593910266"
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_simulate_message_resumes_wait_user_with_same_sim_id():
    """
    Flow: telegram_trigger → wait_user → reply. El primer turno queda
    parqueado en wait_user; el segundo turno con el mismo sim_id debe
    reanudar y producir reply.
    """
    definition = {
        "nodes": [
            {"id": "trigger1", "type": "telegram_trigger", "config": {}},
            {"id": "wait1", "type": "wait_user", "config": {}},
            {"id": "reply1", "type": "send_message", "config": {"message": "recibido: {{conversation.last}}"}},
        ],
        "edges": [
            {"source": "trigger1", "target": "wait1"},
            {"source": "wait1", "target": "reply1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    flow = await svc.create_flow(
        bot_id=BOT_ID_SIM, name="Con wait_user", definition=definition,
        connection_id="conn-1", contact_phone=None, contact_filter=None,
    )
    try:
        first = await svc.simulate_message(bot_id=BOT_ID_SIM, message="hola")
        assert first["ok"] is True
        assert first["reply"] is None  # bloqueado en wait_user, sin reply todavía

        second = await svc.simulate_message(
            bot_id=BOT_ID_SIM, message="segundo mensaje", sim_id=first["sim_id"],
        )
        assert second["ok"] is True
        assert second["reply"] == "recibido: segundo mensaje"
        assert second["sim_id"] == first["sim_id"]
    finally:
        await _cleanup(flow["id"])


BOT_ID_NF = "__test_bot_nodoflow_business__"


@pytest.mark.asyncio
async def test_create_flow_persists_flow_kind():
    flow = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Un NodoFlow", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
        flow_kind="node_flow",
    )
    try:
        assert flow["flow_kind"] == "node_flow"
        fetched = await svc.get_flow(flow["id"], BOT_ID_NF)
        assert fetched["flow_kind"] == "node_flow"
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_create_flow_default_flow_kind_is_flow():
    flow = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Normal", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        assert flow["flow_kind"] == "flow"
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_update_flow_can_change_flow_kind():
    flow = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Cambia de tipo", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        updated = await svc.update_flow(BOT_ID_NF, flow["id"], {"flow_kind": "node_flow"})
        assert updated["flow_kind"] == "node_flow"
    finally:
        await _cleanup(flow["id"])


@pytest.mark.asyncio
async def test_create_flow_con_nodo_flow_autoreferenciado_rechaza_ciclo():
    """Un flow que se guarda con un nodo `nodo_flow` que termina apuntando
    (directa o indirectamente) a sí mismo debe rechazarse con ValueError
    claro — no dejar pasar el ValueError crudo de expand_node_flows."""
    # Un create nuevo no puede autoreferenciarse (no tiene id todavía) —
    # forzamos el ciclo con un sub-flow ya persistido que se referencia a sí
    # mismo, que es el caso real detectable en el momento del save.
    self_ref = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Self ref (crudo, sin validar)", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
        flow_kind="node_flow",
    )
    try:
        cyclic_definition = {
            "nodes": [{"id": "a", "type": "nodo_flow", "config": {"flow_id": self_ref["id"]}}],
            "edges": [],
        }
        # Escribimos el ciclo directo en la propia definition del sub-flow vía
        # db (bypaseando la validación de negocio) para simular un flow ya
        # guardado con un ciclo, y confirmar que un update posterior también
        # lo detecta si se re-guarda con el mismo contenido.
        await db.update_flow(self_ref["id"], definition=cyclic_definition)
        with pytest.raises(ValueError, match="NodoFlow inválido"):
            await svc.update_flow(
                BOT_ID_NF, self_ref["id"],
                {"definition": cyclic_definition},
            )
    finally:
        await _cleanup(self_ref["id"])


@pytest.mark.asyncio
async def test_list_node_flows_devuelve_solo_flow_kind_node_flow_con_inputs():
    normal = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Flow normal", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    node_flow_def = {
        "inputs": [{"key": "ciudad", "label": "Ciudad", "type": "text", "default": ""}],
        "nodes": [], "edges": [],
    }
    nf = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Investigar", definition=node_flow_def,
        connection_id=None, contact_phone=None, contact_filter=None,
        flow_kind="node_flow",
    )
    nf_sin_inputs = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Sin inputs", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
        flow_kind="node_flow",
    )
    try:
        result = await svc.list_node_flows(BOT_ID_NF)
        by_id = {f["id"]: f for f in result}
        assert normal["id"] not in by_id
        assert nf["id"] in by_id
        assert by_id[nf["id"]]["inputs"] == node_flow_def["inputs"]
        assert nf_sin_inputs["id"] in by_id
        assert by_id[nf_sin_inputs["id"]]["inputs"] == []
    finally:
        await _cleanup(normal["id"], nf["id"], nf_sin_inputs["id"])


@pytest.mark.asyncio
async def test_create_node_flow_from_selection_extrae_subgrafo():
    source_definition = {
        "nodes": [
            {"id": "t", "type": "message_trigger", "config": {}},
            {"id": "a", "type": "llm", "config": {}},
            {"id": "b", "type": "send_message", "config": {}},
            {"id": "c", "type": "set_state", "config": {"field": "x", "value": "1"}},
        ],
        "edges": [
            {"source": "t", "target": "a"},
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
        ],
    }
    source = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Origen", definition=source_definition,
        connection_id="conn-1", contact_phone=None, contact_filter=None,
    )
    try:
        extracted = await svc.create_node_flow_from_selection(
            bot_id=BOT_ID_NF, source_flow_id=source["id"],
            node_ids=["a", "b"], name="Extraído a-b",
        )
        try:
            assert extracted["flow_kind"] == "node_flow"
            assert extracted["active"] is False
            node_ids = {n["id"] for n in extracted["definition"]["nodes"]}
            assert node_ids == {"a", "b"}
            edges = extracted["definition"]["edges"]
            assert edges == [{"source": "a", "target": "b"}]

            # El flow origen queda intacto.
            still_there = await svc.get_flow(source["id"], BOT_ID_NF)
            assert len(still_there["definition"]["nodes"]) == 4
            assert len(still_there["definition"]["edges"]) == 3
        finally:
            await _cleanup(extracted["id"])
    finally:
        await _cleanup(source["id"])


@pytest.mark.asyncio
async def test_create_node_flow_from_selection_node_ids_vacio_falla():
    source = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Origen vacío", definition=None,
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        with pytest.raises(ValueError):
            await svc.create_node_flow_from_selection(
                bot_id=BOT_ID_NF, source_flow_id=source["id"], node_ids=[], name="X",
            )
    finally:
        await _cleanup(source["id"])


@pytest.mark.asyncio
async def test_create_node_flow_from_selection_node_ids_sin_match_falla():
    source_definition = {
        "nodes": [{"id": "a", "type": "llm", "config": {}}],
        "edges": [],
    }
    source = await svc.create_flow(
        bot_id=BOT_ID_NF, name="Origen sin match", definition=source_definition,
        connection_id=None, contact_phone=None, contact_filter=None,
    )
    try:
        with pytest.raises(ValueError):
            await svc.create_node_flow_from_selection(
                bot_id=BOT_ID_NF, source_flow_id=source["id"],
                node_ids=["no-existe"], name="X",
            )
    finally:
        await _cleanup(source["id"])


@pytest.mark.asyncio
async def test_create_node_flow_from_selection_flow_origen_no_encontrado():
    with pytest.raises(ValueError):
        await svc.create_node_flow_from_selection(
            bot_id=BOT_ID_NF, source_flow_id="no-existe", node_ids=["a"], name="X",
        )


@pytest.mark.asyncio
async def test_migrate_fetch_node_types_es_idempotente():
    definition = {
        "nodes": [{"id": "buscar_fb", "type": "fetch", "config": {"source": "facebook"}}],
        "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    flow = await svc.create_flow(
        bot_id=BOT_ID, name="Idempotencia", definition=definition,
        connection_id="conn-1", contact_phone=None, contact_filter=None,
    )
    try:
        await svc.migrate_fetch_node_types()
        await svc.migrate_fetch_node_types()  # segunda corrida no debe romper nada
        migrated = await svc.get_flow(flow["id"], BOT_ID)
        assert migrated["definition"]["nodes"][0]["type"] == "fetch_http"
    finally:
        await _cleanup(flow["id"])
