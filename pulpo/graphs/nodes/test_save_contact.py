"""Tests unitarios para SaveContactNode."""
from unittest.mock import AsyncMock, patch

import pytest

from .save_contact import SaveContactNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


@pytest.mark.asyncio
async def test_persiste_contacto_nuevo():
    node = SaveContactNode({})
    with patch("pulpo.core.db.find_contact_by_channel", new_callable=AsyncMock, return_value=None) as mock_find, \
         patch("pulpo.core.db.create_contact", new_callable=AsyncMock, return_value="c1") as mock_create, \
         patch("pulpo.core.db.add_channel", new_callable=AsyncMock) as mock_add:
        await node.run(_state())

    mock_find.assert_awaited_once()
    mock_create.assert_awaited_once()
    mock_add.assert_awaited_once()


@pytest.mark.asyncio
async def test_sim_no_persiste_nada(caplog):
    """En simulación (_sim=True): no INSERT/UPDATE real — solo log."""
    node = SaveContactNode({})
    state = _state()
    state.data["_sim"] = True
    with patch("pulpo.core.db.find_contact_by_channel", new_callable=AsyncMock) as mock_find, \
         patch("pulpo.core.db.create_contact", new_callable=AsyncMock) as mock_create, \
         patch("pulpo.core.db.update_contact", new_callable=AsyncMock) as mock_update, \
         caplog.at_level("INFO"):
        await node.run(state)

    mock_find.assert_not_awaited()
    mock_create.assert_not_awaited()
    mock_update.assert_not_awaited()
    assert any("[sim]" in r.message for r in caplog.records)
