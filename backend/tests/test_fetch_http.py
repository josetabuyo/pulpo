"""
Tests for FetchNode source=http with URL template substitution.
No server required — uses httpx mocks.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from graphs.nodes.fetch import FetchNode
from graphs.nodes.state import FlowState


def make_node(url: str, extract: str = "json") -> FetchNode:
    return FetchNode(config={"source": "http", "url": url, "extract": extract})


def make_state(message: str = "donde hay una ferreteria", query: str = "") -> FlowState:
    s = FlowState(message=message, bot_id="luganense")
    if query:
        s.data["query"] = query
    return s


def mock_response(body: str, status: int = 200):
    resp = MagicMock()
    resp.text = body
    resp.raise_for_status = MagicMock()
    return resp


# ── URL template substitution ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_template_substituted():
    """{message} in URL is replaced with state.message before the GET request."""
    node = make_node("https://api.example.com/buscar?q={message}")
    state = make_state(message="ferreteria")

    captured_url = {}

    async def fake_get(url, **_):
        captured_url["url"] = url
        return mock_response('{"results": []}')

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(side_effect=fake_get)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        await node.run(state)

    assert captured_url["url"] == "https://api.example.com/buscar?q=ferreteria"


@pytest.mark.asyncio
async def test_query_template_substituted_when_set():
    """{query} uses state.query when present."""
    node = make_node("https://api.example.com/buscar?q={query}")
    state = make_state(message="donde hay una ferreteria", query="ferreteria")

    captured_url = {}

    async def fake_get(url, **_):
        captured_url["url"] = url
        return mock_response('{"results": []}')

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(side_effect=fake_get)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        await node.run(state)

    assert captured_url["url"] == "https://api.example.com/buscar?q=ferreteria"


@pytest.mark.asyncio
async def test_query_falls_back_to_message_when_empty():
    """{query} falls back to state.message when state.query is empty."""
    node = make_node("https://api.example.com/buscar?q={query}")
    state = make_state(message="panaderia", query="")

    captured_url = {}

    async def fake_get(url, **_):
        captured_url["url"] = url
        return mock_response('{"results": []}')

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(side_effect=fake_get)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        await node.run(state)

    assert captured_url["url"] == "https://api.example.com/buscar?q=panaderia"


@pytest.mark.asyncio
async def test_no_template_url_unchanged():
    """Static URLs without templates are sent as-is."""
    node = make_node("https://api.example.com/data")
    state = make_state(message="algo")

    captured_url = {}

    async def fake_get(url, **_):
        captured_url["url"] = url
        return mock_response('[]')

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(side_effect=fake_get)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        await node.run(state)

    assert captured_url["url"] == "https://api.example.com/data"


# ── JSON response stored in context ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_json_response_stored_in_context():
    """With extract=json the raw JSON string is stored in state.context."""
    node = make_node("https://api.example.com/buscar?q={message}", extract="json")
    state = make_state(message="kiosco")
    payload = '{"results": [{"nombre": "Kiosco Don Jorge"}], "total": 1}'

    async def fake_get(url, **_):
        return mock_response(payload)

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(side_effect=fake_get)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        await node.run(state)

    assert state.data.get("context") == payload


# ── Error resilience ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_http_error_does_not_raise():
    """Network errors are caught and logged — state.context stays empty."""
    node = make_node("https://api.example.com/buscar?q={message}")
    state = make_state(message="algo")

    async def fake_get(url, **_):
        raise Exception("connection refused")

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(side_effect=fake_get)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        await node.run(state)  # must not raise

    assert state.data.get("context", "") == ""


@pytest.mark.asyncio
async def test_missing_url_does_nothing():
    """If url config is empty the node skips silently."""
    node = FetchNode(config={"source": "http", "url": "", "extract": "json"})
    state = make_state()
    await node.run(state)
    assert state.data.get("context", "") == ""


# ── extract_first_to_vars + contactos expansion ──────────────────────────────

@pytest.mark.asyncio
async def test_extract_first_to_vars_expands_contactos():
    """contactos: [{tipo, valor}] se expande a vars planos por tipo."""
    node = FetchNode(config={
        "source": "http",
        "url": "https://api.example.com/buscar?q={message}",
        "extract": "json",
        "extract_first_result_to_vars": True,
    })
    state = make_state(message="plomero")
    payload = '{"results": [{"nombre": "Juan", "contactos": [{"tipo": "whatsapp", "valor": "1155551234"}, {"tipo": "telegram", "valor": "98765"}]}]}'

    async def fake_get(url, **_):
        return mock_response(payload)

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(side_effect=fake_get)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        await node.run(state)

    assert state.data.get("nombre") == "Juan"
    assert state.data.get("whatsapp") == "1155551234"
    assert state.data.get("telegram") == "98765"


# ── Config schema ────────────────────────────────────────────────────────────

def test_config_schema_has_url_hint_with_templates():
    schema = FetchNode.config_schema()
    hint = schema["url"]["hint"]
    assert "{message}" in hint
    assert "{query}" in hint
