"""Tests unitarios para MetricNode."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from .metric import MetricNode
from .state import FlowState, append_conversation_entry


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


@pytest.mark.asyncio
async def test_persiste_metrica_basica():
    node = MetricNode({"metric_name": "intencion_detectada", "value": "reserva"})
    with patch("pulpo.core.db.insert_metric", new_callable=AsyncMock) as mock_insert:
        await node.run(_state())

    mock_insert.assert_awaited_once()
    kwargs = mock_insert.call_args.kwargs
    assert kwargs["metric_name"] == "intencion_detectada"
    assert kwargs["value"] == "reserva"
    assert kwargs["bot_id"] == "bot1"
    assert kwargs["contact_phone"] == "user1"
    assert kwargs["metadata"] is None


@pytest.mark.asyncio
async def test_metric_name_vacio_no_persiste():
    node = MetricNode({"metric_name": "", "value": "x"})
    with patch("pulpo.core.db.insert_metric", new_callable=AsyncMock) as mock_insert:
        await node.run(_state())

    mock_insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_templates_en_metric_name_y_value():
    node = MetricNode({"metric_name": "canal_{{canal}}", "value": "{{conversation.last}}"})
    state = _state()
    append_conversation_entry(state, "user", "quiero reservar")
    with patch("pulpo.core.db.insert_metric", new_callable=AsyncMock) as mock_insert:
        await node.run(state)

    kwargs = mock_insert.call_args.kwargs
    assert kwargs["metric_name"] == "canal_telegram"
    assert kwargs["value"] == "quiero reservar"


@pytest.mark.asyncio
async def test_metadata_se_serializa_con_templates():
    node = MetricNode({
        "metric_name": "m",
        "value": "v",
        "metadata": {"contacto": "{{contact_name}}"},
    })
    with patch("pulpo.core.db.insert_metric", new_callable=AsyncMock) as mock_insert:
        await node.run(_state())

    kwargs = mock_insert.call_args.kwargs
    assert json.loads(kwargs["metadata"]) == {"contacto": "Juan"}


@pytest.mark.asyncio
async def test_webhook_ok_no_afecta_persistencia():
    node = MetricNode({"metric_name": "m", "value": "v", "webhook_url": "http://ext.local/hook"})
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    with patch("pulpo.core.db.insert_metric", new_callable=AsyncMock) as mock_insert, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        state = await node.run(_state())

    mock_insert.assert_awaited_once()
    mock_client.post.assert_awaited_once()
    assert state.data == {}


@pytest.mark.asyncio
async def test_sim_no_persiste_ni_llama_webhook(caplog):
    """En simulación (_sim=True): no INSERT en DB, no webhook — solo log."""
    node = MetricNode({"metric_name": "m", "value": "v", "webhook_url": "http://ext.local/hook"})
    state = _state()
    state.data["_sim"] = True
    with patch("pulpo.core.db.insert_metric", new_callable=AsyncMock) as mock_insert, \
         patch("httpx.AsyncClient") as mock_client_cls, \
         caplog.at_level("INFO"):
        await node.run(state)

    mock_insert.assert_not_awaited()
    mock_client_cls.assert_not_called()
    assert any("[sim]" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_webhook_falla_no_interrumpe_el_flow(caplog):
    node = MetricNode({"metric_name": "m", "value": "v", "webhook_url": "http://ext.local/hook"})
    with patch("pulpo.core.db.insert_metric", new_callable=AsyncMock) as mock_insert, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        with caplog.at_level("ERROR"):
            state = await node.run(_state())

    mock_insert.assert_awaited_once()
    assert state is not None
    assert any("webhook falló" in r.message for r in caplog.records)
