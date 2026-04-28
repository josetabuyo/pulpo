"""
Tests para FetchSheetNode.
No requieren server corriendo — usan mocks de httpx.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from graphs.nodes.fetch_sheet import FetchSheetNode, _sheet_cache, _build_url, _csv_to_format
from graphs.nodes.state import FlowState


CSV_SAMPLE = "nombre,oficio,precio\nGregorio,herrero,500\nAna,abogada,800\n"


def make_state() -> FlowState:
    return FlowState(
        message="quiero un herrero",
        empresa_id="test",
        connection_id="test",
        canal="whatsapp",
    )


def make_mock_response(text: str, status: int = 200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


# ── Tests de _csv_to_format ───────────────────────────────────────────────────

def test_csv_to_markdown():
    result = _csv_to_format(CSV_SAMPLE, "markdown_table")
    assert "| nombre |" in result
    assert "| Gregorio |" in result
    assert "---" in result


def test_csv_to_json():
    result = _csv_to_format(CSV_SAMPLE, "json")
    import json
    rows = json.loads(result)
    assert len(rows) == 2
    assert rows[0]["oficio"] == "herrero"


def test_csv_to_plain_text():
    result = _csv_to_format(CSV_SAMPLE, "plain_text")
    assert "Gregorio" in result
    assert "|" in result


def test_csv_empty():
    result = _csv_to_format("", "markdown_table")
    assert result == ""


# ── Tests del nodo ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_sheet_vuelca_en_context():
    _sheet_cache.clear()
    node = FetchSheetNode({"sheet_id": "abc123", "cache_minutes": 0})
    state = make_state()

    mock_resp = make_mock_response(CSV_SAMPLE)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("graphs.nodes.fetch_sheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert "Gregorio" in result.context
    assert result.context.startswith("|")  # markdown_table


@pytest.mark.asyncio
async def test_fetch_sheet_output_vars():
    _sheet_cache.clear()
    node = FetchSheetNode({"sheet_id": "abc123", "output": "vars.sheet_data", "cache_minutes": 0})
    state = make_state()

    mock_resp = make_mock_response(CSV_SAMPLE)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("graphs.nodes.fetch_sheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert "sheet_data" in result.vars
    assert "Gregorio" in result.vars["sheet_data"]
    assert result.context == ""  # no tocó context


@pytest.mark.asyncio
async def test_fetch_sheet_cache_evita_segunda_llamada():
    _sheet_cache.clear()
    node = FetchSheetNode({"sheet_id": "sheet_cache_test", "cache_minutes": 5})
    state = make_state()

    mock_resp = make_mock_response(CSV_SAMPLE)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("graphs.nodes.fetch_sheet.httpx.AsyncClient", return_value=mock_client):
        await node.run(state)
        await node.run(make_state())

    # Solo se hizo una llamada HTTP real
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_fetch_sheet_sin_cache():
    _sheet_cache.clear()
    node = FetchSheetNode({"sheet_id": "sheet_nocache", "cache_minutes": 0})

    mock_resp = make_mock_response(CSV_SAMPLE)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("graphs.nodes.fetch_sheet.httpx.AsyncClient", return_value=mock_client):
        await node.run(make_state())
        await node.run(make_state())

    assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_sheet_sin_sheet_id():
    node = FetchSheetNode({"sheet_id": ""})
    state = make_state()
    result = await node.run(state)
    assert result.context == ""


def test_build_url_sin_range():
    url = _build_url("myid", "")
    assert url == "https://docs.google.com/spreadsheets/d/myid/export?format=csv"


def test_build_url_con_range():
    url = _build_url("myid", "A1:D10")
    assert "range=A1:D10" in url


def test_config_schema():
    schema = FetchSheetNode.config_schema()
    assert "sheet_id" in schema
    assert "cache_minutes" in schema
    assert schema["format"]["default"] == "markdown_table"
