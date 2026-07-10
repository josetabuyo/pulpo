"""Tests unitarios para GSheetNode (modo append + guard de simulación)."""
from unittest.mock import MagicMock, patch

import pytest

from .gsheet import GSheetNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


@pytest.mark.asyncio
async def test_sim_no_hace_post_real(caplog):
    """En simulación (_sim=True): append no debe llamar a la API de Sheets — solo loguear el payload."""
    node = GSheetNode({
        "mode": "append",
        "sheet_id": "sheet123",
        "sheet_name": "Hoja1",
        "columns": [{"header": "nombre", "source": "vars.nombre"}],
    })
    state = _state()
    state.data["_sim"] = True
    state.data["nombre"] = "Pedro"

    # Sin credenciales configuradas — igual no debe fallar ni intentar el POST,
    # el guard de sim corta antes de resolver credenciales.
    with patch("googleapiclient.discovery.build") as mock_build, caplog.at_level("INFO"):
        await node.run(state)

    mock_build.assert_not_called()
    assert any("[sim]" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_append_real_llama_a_sheets_api():
    node = GSheetNode({
        "mode": "append",
        "sheet_id": "sheet123",
        "sheet_name": "Hoja1",
        "columns": [{"header": "nombre", "source": "vars.nombre"}],
    })
    state = _state()
    state.data["nombre"] = "Pedro"

    fake_sa = '{"client_email": "x@y.com", "token_uri": "https://oauth2.googleapis.com/token", "private_key": "x"}'
    mock_service = MagicMock()
    with patch("pulpo.graphs.nodes.gsheet._resolve_credentials", return_value=fake_sa), \
         patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("googleapiclient.discovery.build", return_value=mock_service) as mock_build:
        await node.run(state)

    mock_build.assert_called_once()
    mock_service.spreadsheets.return_value.values.return_value.append.assert_called_once()
