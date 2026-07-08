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
async def test_migrate_fetch_node_types_separa_por_source():
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

        assert by_id["buscar_fb"]["type"] == "fetch_fb"
        assert "source" not in by_id["buscar_fb"]["config"]
        assert by_id["buscar_dir"]["type"] == "fetch_http"
        assert "source" not in by_id["buscar_dir"]["config"]
        assert by_id["buscar_default"]["type"] == "fetch_fb"  # default histórico era "facebook"
        assert by_id["otro"]["type"] == "llm"  # no tocado
    finally:
        await _cleanup(flow["id"])


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
        assert migrated["definition"]["nodes"][0]["type"] == "fetch_fb"
    finally:
        await _cleanup(flow["id"])
