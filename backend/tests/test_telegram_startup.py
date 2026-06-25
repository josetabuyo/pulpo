"""
Tests unitarios para _start_tg_bot — la función que maneja el arranque de bots
de Telegram con retry y manejo de errores.

No requieren servidor corriendo: todo se ejecuta con mocks de AsyncMock.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from telegram.error import TimedOut, NetworkError

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import _start_tg_bot


CFG = {
    "connection_id": "bot_test",
    "token": "123456:AAABBBCCC",
    "reply_message": "Hola",
}


def _mock_bot_info(username="testbot", first_name="Test Bot"):
    info = MagicMock()
    info.username = username
    info.first_name = first_name
    return info


def _make_tg_app(
    initialize_side_effect=None,
    start_side_effect=None,
    polling_side_effect=None,
    get_me_result=None,
):
    """Construye un Application mock configurable."""
    app = MagicMock()
    app.initialize = AsyncMock(side_effect=initialize_side_effect)
    app.start = AsyncMock(side_effect=start_side_effect)
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()

    updater = MagicMock()
    updater.start_polling = AsyncMock(side_effect=polling_side_effect)
    updater.stop = AsyncMock()
    app.updater = updater

    bot = MagicMock()
    bot.get_me = AsyncMock(return_value=get_me_result or _mock_bot_info())
    app.bot = bot

    return app


@pytest.mark.asyncio
async def test_happy_path_retorna_tuple():
    """Cuando todo funciona, retorna (tg_app, session_id, bot_info)."""
    mock_app = _make_tg_app()

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        result = await _start_tg_bot(CFG)

    assert result is not None
    tg_app, session_id, bot_info = result
    assert tg_app is mock_app
    assert session_id == "bot_test-tg-123456"
    assert bot_info.username == "testbot"


@pytest.mark.asyncio
async def test_initialize_timeout_retorna_none_y_no_crashea():
    """Si initialize() da timeout en todos los intentos, retorna None sin crashear."""
    mock_app = _make_tg_app(initialize_side_effect=TimedOut("timeout"))

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        result = await _start_tg_bot(CFG)

    assert result is None
    assert mock_app.initialize.call_count == 3


@pytest.mark.asyncio
async def test_initialize_timeout_luego_exito_conecta(caplog):
    """Si initialize() falla 2 veces y luego funciona, el bot conecta correctamente."""
    call_count = 0

    async def flaky_initialize():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimedOut("timeout")

    mock_app = _make_tg_app()
    mock_app.initialize = AsyncMock(side_effect=flaky_initialize)

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        result = await _start_tg_bot(CFG)

    assert result is not None
    assert call_count == 3


@pytest.mark.asyncio
async def test_initialize_timeout_loguea_error_digerido(caplog):
    """Cuando initialize falla, el log debe mostrar un mensaje claro (no el traceback crudo)."""
    import logging
    mock_app = _make_tg_app(initialize_side_effect=TimedOut("timeout"))

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock), \
         caplog.at_level(logging.ERROR, logger="main"):
        await _start_tg_bot(CFG)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    msg = errors[0].message
    assert "api.telegram.org" in msg or "token" in msg
    assert "El bot se omite" in msg


@pytest.mark.asyncio
async def test_start_falla_retorna_none():
    """Si start() falla después de un initialize() exitoso, retorna None."""
    mock_app = _make_tg_app(start_side_effect=Exception("dispatcher error"))

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        result = await _start_tg_bot(CFG)

    assert result is None
    mock_app.initialize.assert_awaited_once()
    mock_app.start.assert_awaited_once()
    # shutdown debe haberse llamado para limpiar
    mock_app.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_polling_falla_retorna_none():
    """Si start_polling() falla en todos los intentos, retorna None y hace cleanup."""
    mock_app = _make_tg_app(polling_side_effect=NetworkError("network"))

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        result = await _start_tg_bot(CFG)

    assert result is None
    assert mock_app.updater.start_polling.call_count == 3
    mock_app.stop.assert_awaited_once()
    mock_app.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_network_error_en_initialize_tratado_igual_que_timeout():
    """NetworkError durante initialize también debe recuperarse con retry."""
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise NetworkError("connection refused")

    mock_app = _make_tg_app()
    mock_app.initialize = AsyncMock(side_effect=flaky)

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        result = await _start_tg_bot(CFG)

    assert result is not None
    assert call_count == 2


@pytest.mark.asyncio
async def test_get_me_falla_retorna_none():
    """Si get_me() falla tras polling exitoso, retorna None y hace cleanup completo."""
    mock_app = _make_tg_app(get_me_result=None)
    mock_app.bot.get_me = AsyncMock(side_effect=TimedOut("timeout"))

    with patch("main.build_telegram_app", return_value=mock_app), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        result = await _start_tg_bot(CFG)

    assert result is None
    mock_app.updater.stop.assert_awaited_once()
    mock_app.stop.assert_awaited_once()
    mock_app.shutdown.assert_awaited_once()
