"""
TDD — Fase 1: define el contrato de automation/sync.py antes de que exista.
Todos los tests deben fallar con ImportError hasta que Fase 2 implemente sync.py.

Convención de patches: sync.py importará las funciones directamente:
    from graphs.nodes.summarize import accumulate, clear_contact, _newest_message_ts
→ patch path: "automation.sync.<nombre>"
"""
import asyncio
import inspect
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _msg(body="hola", sender="Andrés Buxareo", is_outbound=False,
         timestamp="2026-05-10 10:00:00", msg_type="text",
         quoted="", quoted_sender=""):
    return {
        "body": body,
        "sender": sender,
        "is_outbound": is_outbound,
        "timestamp": timestamp,
        "msg_type": msg_type,
        "quoted": quoted,
        "quotedSender": quoted_sender,
    }


def _out(body="respuesta", sender="Jozbuyo", timestamp="2026-05-10 11:00:00"):
    return _msg(body=body, sender=sender, is_outbound=True, timestamp=timestamp)


def _mock_session(messages=None):
    s = MagicMock()
    s.scrape_full_history_v2 = AsyncMock(return_value=messages or [])
    return s


# ─── Módulo: StopCondition ───────────────────────────────────────────────────

def test_stop_condition_tiene_tres_valores():
    from automation.sync import StopCondition
    assert StopCondition.FULL_OVERWRITE
    assert StopCondition.FULL_ENRICH
    assert StopCondition.UNTIL_KNOWN


# ─── Módulo: delta_sync firma ────────────────────────────────────────────────

def test_delta_sync_es_async():
    from automation.sync import delta_sync
    assert inspect.iscoroutinefunction(delta_sync)


def test_delta_sync_tiene_params_obligatorios():
    from automation.sync import delta_sync
    params = inspect.signature(delta_sync).parameters
    for p in ("wa_session", "session_id", "contact_name",
              "empresa_id", "contact_phone", "stop_condition"):
        assert p in params, f"Falta parámetro obligatorio: '{p}'"


def test_delta_sync_tiene_params_opcionales():
    from automation.sync import delta_sync
    params = inspect.signature(delta_sync).parameters
    for p in ("since_date", "owner_name", "on_progress"):
        assert p in params, f"Falta parámetro opcional: '{p}'"


# ─── Resultado ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retorna_dict_con_claves_esperadas():
    from automation.sync import delta_sync, StopCondition
    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact"):
        result = await delta_sync(
            wa_session=_mock_session(),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.UNTIL_KNOWN,
        )
    assert isinstance(result, dict)
    assert "scraped" in result
    assert "new" in result
    assert "stop_reason" in result


@pytest.mark.asyncio
async def test_scraped_cuenta_mensajes_del_scraper():
    from automation.sync import delta_sync, StopCondition
    msgs = [_msg(body=f"msg {i}", timestamp=f"2026-05-10 10:0{i}:00") for i in range(5)]
    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact"):
        result = await delta_sync(
            wa_session=_mock_session(msgs),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
        )
    assert result["scraped"] == 5


# ─── UNTIL_KNOWN ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_until_known_pasa_newest_ts_como_stop():
    """Con UNTIL_KNOWN, el stop_before_ts que se pasa al scraper = _newest_message_ts()."""
    from automation.sync import delta_sync, StopCondition
    session = _mock_session()
    known_ts = datetime(2026, 5, 8, 10, 0)

    with patch("automation.sync.accumulate"), \
         patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=known_ts):
        await delta_sync(
            wa_session=session,
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.UNTIL_KNOWN,
        )

    kwargs = session.scrape_full_history_v2.call_args.kwargs
    assert kwargs.get("stop_before_ts") == known_ts


@pytest.mark.asyncio
async def test_until_known_sin_historial_pasa_none():
    """Con UNTIL_KNOWN y sin historial previo, stop_before_ts=None (scrapeamos todo)."""
    from automation.sync import delta_sync, StopCondition
    session = _mock_session()

    with patch("automation.sync.accumulate"), \
         patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None):
        await delta_sync(
            wa_session=session,
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.UNTIL_KNOWN,
        )

    kwargs = session.scrape_full_history_v2.call_args.kwargs
    assert kwargs.get("stop_before_ts") is None


@pytest.mark.asyncio
async def test_until_known_no_borra_md():
    """Con UNTIL_KNOWN nunca se llama clear_contact."""
    from automation.sync import delta_sync, StopCondition

    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact") as mock_clear:
        await delta_sync(
            wa_session=_mock_session(),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.UNTIL_KNOWN,
        )

    mock_clear.assert_not_called()


# ─── FULL_OVERWRITE ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_overwrite_llama_clear_antes_de_scrape():
    """Con FULL_OVERWRITE, clear_contact() se llama antes que scrape_full_history_v2."""
    from automation.sync import delta_sync, StopCondition
    session = _mock_session()
    call_order = []
    session.scrape_full_history_v2 = AsyncMock(
        side_effect=lambda *a, **kw: call_order.append("scrape") or []
    )

    def _fake_clear(eid, cp):
        call_order.append("clear")

    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact", side_effect=_fake_clear):
        await delta_sync(
            wa_session=session,
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_OVERWRITE,
        )

    assert call_order[0] == "clear", "clear_contact debe llamarse antes del scrape"
    assert "scrape" in call_order


@pytest.mark.asyncio
async def test_full_overwrite_clear_recibe_empresa_y_phone():
    """clear_contact recibe los parámetros correctos."""
    from automation.sync import delta_sync, StopCondition

    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact") as mock_clear:
        await delta_sync(
            wa_session=_mock_session(),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="garantido",
            contact_phone="andres-buxareo",
            stop_condition=StopCondition.FULL_OVERWRITE,
        )

    mock_clear.assert_called_once_with("garantido", "andres-buxareo")


@pytest.mark.asyncio
async def test_full_overwrite_since_date_pasa_como_stop():
    """Con FULL_OVERWRITE + since_date, stop_before_ts = since_date."""
    from automation.sync import delta_sync, StopCondition
    session = _mock_session()
    since = datetime(2026, 5, 1)

    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact"):
        await delta_sync(
            wa_session=session,
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_OVERWRITE,
            since_date=since,
        )

    kwargs = session.scrape_full_history_v2.call_args.kwargs
    assert kwargs.get("stop_before_ts") == since


@pytest.mark.asyncio
async def test_full_overwrite_sin_since_date_pasa_none():
    """Con FULL_OVERWRITE sin since_date, stop_before_ts=None (va hasta el tope)."""
    from automation.sync import delta_sync, StopCondition
    session = _mock_session()

    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact"):
        await delta_sync(
            wa_session=session,
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_OVERWRITE,
        )

    kwargs = session.scrape_full_history_v2.call_args.kwargs
    assert kwargs.get("stop_before_ts") is None


# ─── FULL_ENRICH ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_enrich_no_llama_clear():
    """Con FULL_ENRICH, clear_contact() NO se llama."""
    from automation.sync import delta_sync, StopCondition

    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact") as mock_clear:
        await delta_sync(
            wa_session=_mock_session(),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
        )

    mock_clear.assert_not_called()


# ─── Normalización de sender ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_saliente_usa_sender_del_scraper():
    """Mensaje saliente con sender real del scraper → content = 'Jozbuyo: cuerpo'."""
    from automation.sync import delta_sync, StopCondition
    accumulated = []

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate", side_effect=lambda **kw: accumulated.append(kw)):
        await delta_sync(
            wa_session=_mock_session([_out(body="test", sender="Jozbuyo")]),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
            owner_name="Jozbuyo",
        )

    assert len(accumulated) == 1
    assert accumulated[0]["content"].startswith("Jozbuyo:"), accumulated[0]["content"]


@pytest.mark.asyncio
async def test_saliente_sin_sender_usa_owner_name():
    """Mensaje saliente sin sender en scraper → usa owner_name."""
    from automation.sync import delta_sync, StopCondition
    accumulated = []

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate", side_effect=lambda **kw: accumulated.append(kw)):
        await delta_sync(
            wa_session=_mock_session([_out(body="hola", sender="")]),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
            owner_name="Jozbuyo",
        )

    assert len(accumulated) == 1
    assert accumulated[0]["content"].startswith("Jozbuyo:"), accumulated[0]["content"]


@pytest.mark.asyncio
async def test_saliente_sin_sender_ni_owner_name_usa_tu():
    """Mensaje saliente sin sender y sin owner_name → fallback 'Tú'."""
    from automation.sync import delta_sync, StopCondition
    accumulated = []

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate", side_effect=lambda **kw: accumulated.append(kw)):
        await delta_sync(
            wa_session=_mock_session([_out(body="hola", sender="")]),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
            owner_name=None,
        )

    assert len(accumulated) == 1
    assert accumulated[0]["content"].startswith("Tú:"), accumulated[0]["content"]


@pytest.mark.asyncio
async def test_entrante_sin_sender_usa_contact_name():
    """Mensaje entrante sin sender → fallback contact_name."""
    from automation.sync import delta_sync, StopCondition
    accumulated = []

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate", side_effect=lambda **kw: accumulated.append(kw)):
        await delta_sync(
            wa_session=_mock_session([_msg(body="buenas", sender="", is_outbound=False)]),
            session_id="5491155612767",
            contact_name="Andrés Buxareo",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
        )

    assert len(accumulated) == 1
    assert accumulated[0]["content"].startswith("Andrés Buxareo:"), accumulated[0]["content"]


# ─── on_progress callback ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_progress_se_pasa_al_scraper():
    """on_progress se forwarda a scrape_full_history_v2."""
    from automation.sync import delta_sync, StopCondition
    session = _mock_session()
    progress_fn = MagicMock()

    with patch("automation.sync.accumulate"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.clear_contact"):
        await delta_sync(
            wa_session=session,
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
            on_progress=progress_fn,
        )

    kwargs = session.scrape_full_history_v2.call_args.kwargs
    assert kwargs.get("on_progress") is progress_fn


# ─── Acumulación ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accumulate_se_llama_por_cada_mensaje():
    """accumulate() se llama una vez por cada mensaje válido scrapeado."""
    from automation.sync import delta_sync, StopCondition
    msgs = [_msg(body=f"msg {i}") for i in range(3)]

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate") as mock_acc:
        await delta_sync(
            wa_session=_mock_session(msgs),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
        )

    assert mock_acc.call_count == 3


@pytest.mark.asyncio
async def test_accumulate_recibe_empresa_id_y_contact_phone():
    """accumulate() recibe empresa_id y contact_phone correctos."""
    from automation.sync import delta_sync, StopCondition

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate") as mock_acc:
        await delta_sync(
            wa_session=_mock_session([_msg()]),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="garantido",
            contact_phone="andres-buxareo",
            stop_condition=StopCondition.FULL_ENRICH,
        )

    call_kwargs = mock_acc.call_args.kwargs
    assert call_kwargs.get("empresa_id") == "garantido"
    assert call_kwargs.get("contact_phone") == "andres-buxareo"


@pytest.mark.asyncio
async def test_mensajes_con_body_vacio_no_se_acumulan():
    """Mensajes con body vacío se descartan antes de accumulate()."""
    from automation.sync import delta_sync, StopCondition
    msgs = [
        _msg(body="mensaje válido"),
        _msg(body=""),
        _msg(body="   "),
    ]

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate") as mock_acc:
        await delta_sync(
            wa_session=_mock_session(msgs),
            session_id="5491155612767",
            contact_name="Andrés",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
        )

    assert mock_acc.call_count == 1


@pytest.mark.asyncio
async def test_reply_context_se_incluye_en_content():
    """Mensajes con quoted añaden '\\n> ↩ ...' al content de accumulate()."""
    from automation.sync import delta_sync, StopCondition
    msg = _msg(body="lo vi", quoted="el mensaje original", quoted_sender="Andrés")
    accumulated = []

    with patch("automation.sync.clear_contact"), \
         patch("automation.sync._newest_message_ts", return_value=None), \
         patch("automation.sync.accumulate", side_effect=lambda **kw: accumulated.append(kw)):
        await delta_sync(
            wa_session=_mock_session([msg]),
            session_id="5491155612767",
            contact_name="Andrés Buxareo",
            empresa_id="test",
            contact_phone="andres",
            stop_condition=StopCondition.FULL_ENRICH,
        )

    assert len(accumulated) == 1
    content = accumulated[0]["content"]
    assert "> ↩" in content
    assert "el mensaje original" in content
