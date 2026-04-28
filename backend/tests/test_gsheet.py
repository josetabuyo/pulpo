"""
Tests para GSheetNode (modo search).
No requieren server corriendo — usan mocks de httpx.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from graphs.nodes.gsheet import GSheetNode, _rows_cache
from graphs.nodes.state import FlowState


CSV = (
    "oficio,nombre,precio,activo\n"
    "herrero,Gregorio,500,true\n"
    "abogada,Ana,800,true\n"
    "plomero,Carlos,300,false\n"
    "carpintero,María,400,true\n"
)


def make_state(query: str = "herrero", oficio_var: str = "") -> FlowState:
    s = FlowState(message="test", empresa_id="test", connection_id="test", canal="whatsapp")
    s.query = query
    if oficio_var:
        s.vars["oficio"] = oficio_var
    return s


def make_mock_http(csv_text: str):
    resp = MagicMock()
    resp.text = csv_text
    resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=resp)
    return mock_client


# ── search ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_exacto_por_query():
    _rows_cache.clear()
    node = GSheetNode({"sheet_id": "abc", "mode": "search", "search_column": "oficio",
                       "query_source": "query", "cache_minutes": 0})
    state = make_state(query="herrero")
    mock_client = make_mock_http(CSV)

    with patch("graphs.nodes.gsheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert result.vars.get("nombre") == "Gregorio"
    assert result.vars.get("precio") == "500"
    assert "Gregorio" in result.context


@pytest.mark.asyncio
async def test_search_por_vars():
    _rows_cache.clear()
    node = GSheetNode({"sheet_id": "abc", "mode": "search", "search_column": "oficio",
                       "query_source": "vars.oficio", "cache_minutes": 0})
    state = make_state(oficio_var="abogada")
    mock_client = make_mock_http(CSV)

    with patch("graphs.nodes.gsheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert result.vars.get("nombre") == "Ana"


@pytest.mark.asyncio
async def test_search_sin_match_devuelve_disponibles():
    _rows_cache.clear()
    node = GSheetNode({"sheet_id": "abc", "mode": "search", "search_column": "oficio",
                       "query_source": "query", "cache_minutes": 0})
    state = make_state(query="electricista")
    mock_client = make_mock_http(CSV)

    with patch("graphs.nodes.gsheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert result.vars.get("oficio") == "electricista"
    disponibles = json.loads(result.context)
    nombres = [r["nombre"] for r in disponibles]
    assert "Gregorio" in nombres
    assert "Carlos" not in nombres  # activo=false


@pytest.mark.asyncio
async def test_search_filtra_activo_false():
    _rows_cache.clear()
    node = GSheetNode({"sheet_id": "abc", "mode": "search", "search_column": "oficio",
                       "query_source": "query", "cache_minutes": 0})
    state = make_state(query="plomero")
    mock_client = make_mock_http(CSV)

    with patch("graphs.nodes.gsheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert result.vars.get("nombre") is None  # sin match porque activo=false


@pytest.mark.asyncio
async def test_search_contains():
    _rows_cache.clear()
    node = GSheetNode({"sheet_id": "abc", "mode": "search", "search_column": "oficio",
                       "query_source": "query", "exact_match": False, "cache_minutes": 0})
    state = make_state(query="herr")
    mock_client = make_mock_http(CSV)

    with patch("graphs.nodes.gsheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert result.vars.get("nombre") == "Gregorio"


@pytest.mark.asyncio
async def test_search_cache():
    _rows_cache.clear()
    node = GSheetNode({"sheet_id": "cache_gsheet_test", "mode": "search",
                       "search_column": "oficio", "query_source": "query", "cache_minutes": 5})
    mock_client = make_mock_http(CSV)

    with patch("graphs.nodes.gsheet.httpx.AsyncClient", return_value=mock_client):
        await node.run(make_state(query="herrero"))
        await node.run(make_state(query="herrero"))

    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_search_sin_sheet_id():
    node = GSheetNode({"mode": "search", "sheet_id": "", "search_column": "oficio"})
    state = make_state()
    result = await node.run(state)
    assert result.vars == {}


@pytest.mark.asyncio
async def test_search_valor_vacio():
    _rows_cache.clear()
    node = GSheetNode({"sheet_id": "abc", "mode": "search", "search_column": "oficio",
                       "query_source": "query", "cache_minutes": 0})
    state = make_state(query="")  # query vacía
    mock_client = make_mock_http(CSV)

    with patch("graphs.nodes.gsheet.httpx.AsyncClient", return_value=mock_client):
        result = await node.run(state)

    assert result.vars == {}  # no busca si el valor está vacío


def test_config_schema():
    schema = GSheetNode.config_schema()
    assert "mode" in schema
    assert "sheet_id" in schema
    assert "search_column" in schema
    assert "query_source" in schema
    assert "columns" in schema
