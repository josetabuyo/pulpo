"""
Tests para SearchSheetNode.
No requieren server corriendo — usan mocks de httpx y del LLM.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from graphs.nodes.search_sheet import SearchSheetNode, _rows_cache
from graphs.nodes.state import FlowState


CSV_ARTESANOS = (
    "oficio,nombre,precio,activo\n"
    "herrero,Gregorio,500,true\n"
    "abogada,Ana,800,true\n"
    "plomero,Carlos,300,false\n"
    "carpintero,María,400,true\n"
)


def make_state(message: str = "quiero un herrero") -> FlowState:
    return FlowState(
        message=message,
        empresa_id="test",
        connection_id="test",
        canal="whatsapp",
    )


def make_mock_http(csv_text: str):
    resp = MagicMock()
    resp.text = csv_text
    resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=resp)
    return mock_client


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_match_herrero():
    _rows_cache.clear()
    node = SearchSheetNode({"sheet_id": "abc", "search_field": "oficio", "cache_minutes": 0})
    state = make_state("quiero contratar un herrero")
    mock_client = make_mock_http(CSV_ARTESANOS)

    with patch("graphs.nodes.search_sheet.httpx.AsyncClient", return_value=mock_client), \
         patch("graphs.nodes.search_sheet._identify_field_value", new=AsyncMock(return_value="herrero")):
        result = await node.run(state)

    assert result.vars.get("nombre") == "Gregorio"
    assert result.vars.get("oficio") == "herrero"
    assert "Gregorio" in result.context


@pytest.mark.asyncio
async def test_search_normaliza_genero():
    """'herrera' debe matchear 'herrero' por normalización de género."""
    _rows_cache.clear()
    node = SearchSheetNode({"sheet_id": "abc", "search_field": "oficio", "cache_minutes": 0})
    state = make_state("busco una herrera")
    mock_client = make_mock_http(CSV_ARTESANOS)

    with patch("graphs.nodes.search_sheet.httpx.AsyncClient", return_value=mock_client), \
         patch("graphs.nodes.search_sheet._identify_field_value", new=AsyncMock(return_value="herrera")):
        result = await node.run(state)

    assert result.vars.get("nombre") == "Gregorio"


@pytest.mark.asyncio
async def test_search_sin_match():
    _rows_cache.clear()
    node = SearchSheetNode({"sheet_id": "abc", "search_field": "oficio", "cache_minutes": 0})
    state = make_state("busco un electricista")
    mock_client = make_mock_http(CSV_ARTESANOS)

    with patch("graphs.nodes.search_sheet.httpx.AsyncClient", return_value=mock_client), \
         patch("graphs.nodes.search_sheet._identify_field_value", new=AsyncMock(return_value="electricista")):
        result = await node.run(state)

    assert result.vars.get("oficio") == "electricista"
    # context debe tener los ítems activos disponibles
    import json
    disponibles = json.loads(result.context)
    nombres = [r["nombre"] for r in disponibles]
    assert "Gregorio" in nombres
    assert "Ana" in nombres
    assert "María" in nombres
    assert "Carlos" not in nombres  # activo=false, no aparece


@pytest.mark.asyncio
async def test_search_filtra_activo_false():
    """Filas con activo=false no deben aparecer ni en match ni en disponibles."""
    _rows_cache.clear()
    node = SearchSheetNode({"sheet_id": "abc", "search_field": "oficio", "cache_minutes": 0})
    state = make_state("quiero un plomero")
    mock_client = make_mock_http(CSV_ARTESANOS)

    with patch("graphs.nodes.search_sheet.httpx.AsyncClient", return_value=mock_client), \
         patch("graphs.nodes.search_sheet._identify_field_value", new=AsyncMock(return_value="plomero")):
        result = await node.run(state)

    # plomero tiene activo=false → sin match
    assert result.vars.get("nombre") is None
    assert result.vars.get("oficio") == "plomero"
    # Carlos (plomero) no debe aparecer en los disponibles
    import json
    if result.context:
        disponibles = json.loads(result.context)
        assert all(r["nombre"] != "Carlos" for r in disponibles)


@pytest.mark.asyncio
async def test_search_cache_evita_segunda_llamada():
    _rows_cache.clear()
    node = SearchSheetNode({"sheet_id": "cache_test_search", "cache_minutes": 5})
    mock_client = make_mock_http(CSV_ARTESANOS)

    with patch("graphs.nodes.search_sheet.httpx.AsyncClient", return_value=mock_client), \
         patch("graphs.nodes.search_sheet._identify_field_value", new=AsyncMock(return_value="herrero")):
        await node.run(make_state())
        await node.run(make_state())

    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_search_sin_sheet_id():
    node = SearchSheetNode({"sheet_id": ""})
    state = make_state()
    result = await node.run(state)
    assert result.vars == {}
    assert result.context == ""


def test_config_schema():
    schema = SearchSheetNode.config_schema()
    assert "sheet_id" in schema
    assert "search_field" in schema
    assert schema["search_field"]["default"] == "oficio"
