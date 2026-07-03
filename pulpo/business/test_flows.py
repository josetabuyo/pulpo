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
