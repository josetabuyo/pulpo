"""Tests unitarios de EndConversationNode — cierre de open_conversations."""
import json

import pytest

from pulpo.core import db
from .end_conversation import EndConversationNode
from .state import FlowState

_BOT_ID = "__test_bot_end_conv__"
_CONTACT = "__test_contact_end_conv__"


@pytest.fixture(autouse=True)
async def _init_db():
    await db.init_db()


@pytest.mark.asyncio
async def test_end_conversation_borra_open_conversation():
    await db.save_open_conversation(
        bot_id=_BOT_ID, contact_phone=_CONTACT, connection_id="conn1",
        flow_id="flow1", conversation_json=json.dumps([{"turno": 1}]),
    )
    assert await db.get_open_conversation(_BOT_ID, _CONTACT) is not None

    state = FlowState(message="", bot_id=_BOT_ID, contact_phone=_CONTACT)
    node = EndConversationNode({})
    await node.run(state)

    assert await db.get_open_conversation(_BOT_ID, _CONTACT) is None
