"""Tests unitarios para FetchFbNode."""
from unittest.mock import AsyncMock, patch

import pytest

from .fetch_fb import FetchFbNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="luganense", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


def test_config_schema_no_tiene_source():
    schema = FetchFbNode.config_schema()
    assert "source" not in schema
    assert "fb_page_id" in schema
    assert "fb_numeric_id" in schema


@pytest.mark.asyncio
async def test_usa_bot_id_como_page_id_por_defecto():
    fake_posts = AsyncMock(return_value=[{"text": "hola barrio", "url": "https://fb.com/1"}])
    with patch("pulpo.tools.facebook.fetch_facebook.fetch_posts", fake_posts):
        node = FetchFbNode({})
        state = await node.run(_state())

    fake_posts.assert_awaited_once()
    assert fake_posts.call_args.args[0] == "luganense"
    assert "hola barrio" in state.data["context"]


@pytest.mark.asyncio
async def test_dedupe_por_texto_entre_queries():
    async def fake_fetch_posts(page_id, query, numeric_id):
        return [{"text": "mismo post repetido", "url": "https://fb.com/x"}]

    with patch("pulpo.tools.facebook.fetch_facebook.fetch_posts", side_effect=fake_fetch_posts):
        node = FetchFbNode({"fb_page_id": "luganense"})
        state = _state(data={"query": "zanahorias\ncomercio verduras"})
        state = await node.run(state)

    assert len(state.data["fb_posts"]) == 1


@pytest.mark.asyncio
async def test_error_en_scraping_no_rompe_el_flow():
    with patch("pulpo.tools.facebook.fetch_facebook.fetch_posts", side_effect=RuntimeError("boom")):
        node = FetchFbNode({"fb_page_id": "luganense"})
        state = await node.run(_state())

    assert state.data.get("context") is None
