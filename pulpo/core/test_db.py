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
