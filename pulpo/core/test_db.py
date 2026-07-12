"""Tests unitarios de open_conversations (usa la DB sqlite del worktree directamente)."""
import json

import pytest
from sqlalchemy import text

from pulpo.core import db

BOT_ID = "__test_bot_open_conv__"
CONTACT = "__test_contact_open_conv__"


@pytest.fixture(autouse=True)
async def _init_db():
    await db.init_db()


async def _cleanup():
    await db.close_open_conversation(BOT_ID, CONTACT)


@pytest.mark.asyncio
async def test_get_open_conversation_sin_fila_devuelve_none():
    await _cleanup()
    assert await db.get_open_conversation(BOT_ID, CONTACT) is None


@pytest.mark.asyncio
async def test_save_and_get_open_conversation():
    await _cleanup()
    try:
        conv = [{"origin": "user", "content": "hola", "type": "text"}]
        await db.save_open_conversation(
            bot_id=BOT_ID, contact_phone=CONTACT, connection_id="conn1",
            flow_id="flow1", conversation_json=json.dumps(conv),
        )
        row = await db.get_open_conversation(BOT_ID, CONTACT)
        assert row is not None
        assert json.loads(row["conversation_json"]) == conv
        assert row["flow_id"] == "flow1"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_save_open_conversation_es_upsert():
    """Un segundo turno pisa la fila anterior (misma PK bot_id+contact_phone),
    no duplica — es el mecanismo que encadena turnos sin ventana de tiempo."""
    await _cleanup()
    try:
        await db.save_open_conversation(
            bot_id=BOT_ID, contact_phone=CONTACT, connection_id="conn1",
            flow_id="flow1", conversation_json=json.dumps([{"turno": 1}]),
        )
        await db.save_open_conversation(
            bot_id=BOT_ID, contact_phone=CONTACT, connection_id="conn1",
            flow_id="flow1", conversation_json=json.dumps([{"turno": 1}, {"turno": 2}]),
        )
        row = await db.get_open_conversation(BOT_ID, CONTACT)
        assert json.loads(row["conversation_json"]) == [{"turno": 1}, {"turno": 2}]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_close_open_conversation_borra_la_fila():
    await _cleanup()
    await db.save_open_conversation(
        bot_id=BOT_ID, contact_phone=CONTACT, connection_id="conn1",
        flow_id="flow1", conversation_json=json.dumps([{"turno": 1}]),
    )
    assert await db.get_open_conversation(BOT_ID, CONTACT) is not None
    await db.close_open_conversation(BOT_ID, CONTACT)
    assert await db.get_open_conversation(BOT_ID, CONTACT) is None


@pytest.mark.asyncio
async def test_prune_open_conversations_no_toca_las_recientes():
    await _cleanup()
    try:
        await db.save_open_conversation(
            bot_id=BOT_ID, contact_phone=CONTACT, connection_id="conn1",
            flow_id="flow1", conversation_json=json.dumps([{"turno": 1}]),
        )
        # max_age_hours grande: nada tan viejo, no debe podar la fila recién creada.
        await db.prune_open_conversations(max_age_hours=24)
        assert await db.get_open_conversation(BOT_ID, CONTACT) is not None
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_prune_open_conversations_poda_filas_viejas():
    await _cleanup()
    try:
        await db.save_open_conversation(
            bot_id=BOT_ID, contact_phone=CONTACT, connection_id="conn1",
            flow_id="flow1", conversation_json=json.dumps([{"turno": 1}]),
        )
        # Backdate manual — evita flakiness de comparar contra "ahora mismo".
        async with db.AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE open_conversations SET updated_at = datetime('now', '-48 hours')
                    WHERE bot_id=:bot_id AND contact_phone=:contact_phone
                """),
                {"bot_id": BOT_ID, "contact_phone": CONTACT},
            )
            await session.commit()

        n = await db.prune_open_conversations(max_age_hours=24)
        assert n >= 1
        assert await db.get_open_conversation(BOT_ID, CONTACT) is None
    finally:
        await _cleanup()


# ─── flow_versions — historial de guardados (◀ ▶ en el editor) ────────────────
#
# created_at es DATETIME DEFAULT CURRENT_TIMESTAMP, que en SQLite tiene
# resolución de 1 segundo. Si dos versiones se crean dentro del mismo
# segundo (autoguardado + guardado manual, o dos guardados explícitos
# rápidos), "ORDER BY created_at DESC" sin desempate no garantiza que la
# más nueva quede primera. Estos tests fuerzan ese empate a propósito.

FLOW_VERSIONS_BOT_ID = "__test_bot_flow_versions__"


async def _make_flow_with_tied_versions(n=3):
    """Crea un flow y n versiones con el mismo created_at (empate forzado)."""
    flow_id = await db.create_flow(bot_id=FLOW_VERSIONS_BOT_ID, name="v0")
    version_ids = []
    for i in range(n):
        await db.create_flow_version(flow_id, f"v{i+1}", {"nodes": [], "edges": [i]})
        async with db.AsyncSessionLocal() as session:
            row = (await session.execute(
                text("SELECT id FROM flow_versions WHERE flow_id=:flow_id ORDER BY id DESC LIMIT 1"),
                {"flow_id": flow_id},
            )).fetchone()
            version_ids.append(row[0])
    # Empatar todos los created_at al mismo segundo — simula guardados
    # (auto o manual) que caen dentro de la misma ventana de 1s.
    async with db.AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE flow_versions SET created_at = '2026-01-01 00:00:00' WHERE flow_id=:flow_id"),
            {"flow_id": flow_id},
        )
        await session.commit()
    return flow_id, version_ids


@pytest.mark.asyncio
async def test_get_flow_versions_orders_newest_first_despite_tied_timestamps():
    flow_id, version_ids = await _make_flow_with_tied_versions(3)
    try:
        versions = await db.get_flow_versions(flow_id)
        assert [v["id"] for v in versions] == list(reversed(version_ids))
    finally:
        await db.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_create_flow_version_prunes_oldest_id_despite_tied_timestamps():
    flow_id, version_ids = await _make_flow_with_tied_versions(3)
    try:
        # Bajar el límite de poda para el test sin tocar la constante de prod.
        original_limit = db._FLOW_VERSIONS_LIMIT
        db._FLOW_VERSIONS_LIMIT = 2
        try:
            await db.create_flow_version(flow_id, "v4", {"nodes": [], "edges": ["last"]})
        finally:
            db._FLOW_VERSIONS_LIMIT = original_limit

        async with db.AsyncSessionLocal() as session:
            remaining = (await session.execute(
                text("SELECT id FROM flow_versions WHERE flow_id=:flow_id ORDER BY id"),
                {"flow_id": flow_id},
            )).fetchall()
        remaining_ids = [r[0] for r in remaining]
        # Deben sobrevivir las 2 más nuevas: la última creada + la más
        # nueva de las 3 empatadas. Si el desempate fallara, se podría
        # borrar por error la más nueva del empate en vez de la más vieja.
        assert version_ids[-1] in remaining_ids
        assert version_ids[0] not in remaining_ids
        assert len(remaining_ids) == 2
    finally:
        await db.delete_flow(flow_id)


@pytest.mark.asyncio
async def test_get_flow_version_returns_full_definition():
    flow_id, version_ids = await _make_flow_with_tied_versions(1)
    try:
        version = await db.get_flow_version(version_ids[0])
        assert version["flow_id"] == flow_id
        assert version["definition"] == {"nodes": [], "edges": [0]}
    finally:
        await db.delete_flow(flow_id)
