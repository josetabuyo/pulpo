"""
Tests unitarios de graphs/trigger_match.py y graphs/cooldown.py.

Cubren la selección de triggers (canal, connection_id, filtro de contactos,
allow_mass, regex) y el rate limit de replies. Son unitarios puros —
no requieren server corriendo.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, patch

from graphs.cooldown import FlowCooldown, cooldown_hours
from graphs.nodes import NODE_REGISTRY, TRIGGER_TYPES, BaseTriggerNode
from graphs.nodes.state import FlowState
from graphs.trigger_match import _matches_channel, _matches_pattern, select_trigger


# ─── Helpers ──────────────────────────────────────────────────────────────────

CONN = "empresa_test-tg-12345"


def _trigger(ttype="telegram_trigger", **config):
    config.setdefault("connection_id", CONN)
    return {"id": "trigger1", "type": ttype, "config": config}


def _state(canal="telegram", contact="5491199990000", message="Hola"):
    return FlowState(
        message=message,
        contact_phone=contact,
        canal=canal,
        connection_id=CONN,
        empresa_id="empresa_test",
    )


def _no_default_filter():
    """get_connection_default_filter → None (sin default de conexión)."""
    return patch("config.get_connection_default_filter", return_value=None)


# ─── TRIGGER_TYPES derivado del registry ──────────────────────────────────────

def test_trigger_types_derivado_del_registry():
    """No-regresión: los 3 ids históricos siguen siendo triggers."""
    assert TRIGGER_TYPES == {"message_trigger", "telegram_trigger", "whatsapp_trigger"}


def test_trigger_types_son_subclases_de_base_trigger():
    for type_id in TRIGGER_TYPES:
        assert issubclass(NODE_REGISTRY[type_id], BaseTriggerNode), type_id


def test_ningun_nodo_no_trigger_subclasea_base_trigger():
    for type_id, cls in NODE_REGISTRY.items():
        if type_id not in TRIGGER_TYPES:
            assert not issubclass(cls, BaseTriggerNode), type_id


# ─── Match por canal ──────────────────────────────────────────────────────────

def test_telegram_trigger_solo_canal_telegram():
    assert _matches_channel("telegram_trigger", _state(canal="telegram"))
    assert not _matches_channel("telegram_trigger", _state(canal="wavi"))


def test_whatsapp_trigger_solo_canal_wavi():
    assert _matches_channel("whatsapp_trigger", _state(canal="wavi"))
    assert not _matches_channel("whatsapp_trigger", _state(canal="telegram"))


def test_message_trigger_cualquier_canal():
    assert _matches_channel("message_trigger", _state(canal="telegram"))
    assert _matches_channel("message_trigger", _state(canal="wavi"))


# ─── select_trigger: connection_id ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_select_trigger_match_basico():
    with _no_default_filter():
        match = await select_trigger([_trigger()], _state())
    assert match is not None
    assert match.type == "telegram_trigger"
    assert match.node["id"] == "trigger1"


@pytest.mark.asyncio
async def test_select_trigger_sin_connection_id_no_aplica():
    node = _trigger()
    node["config"]["connection_id"] = ""
    assert await select_trigger([node], _state()) is None


@pytest.mark.asyncio
async def test_select_trigger_connection_distinta_no_aplica():
    node = _trigger(connection_id="otra-conexion")
    assert await select_trigger([node], _state()) is None


@pytest.mark.asyncio
async def test_select_trigger_canal_incorrecto_no_aplica():
    with _no_default_filter():
        assert await select_trigger([_trigger("whatsapp_trigger")], _state(canal="telegram")) is None
        assert await select_trigger([_trigger("telegram_trigger")], _state(canal="wavi")) is None


@pytest.mark.asyncio
async def test_select_trigger_primer_candidato_que_aplica_gana():
    """Con un trigger de otro canal y uno correcto, gana el correcto."""
    nodes = [
        _trigger("whatsapp_trigger"),   # no aplica: canal telegram
        _trigger("telegram_trigger"),
    ]
    with _no_default_filter():
        match = await select_trigger(nodes, _state(canal="telegram"))
    assert match is not None
    assert match.type == "telegram_trigger"


# ─── select_trigger: filtro de contactos ──────────────────────────────────────

@pytest.mark.asyncio
async def test_contacto_excluido_no_aplica():
    node = _trigger(contact_filter={"excluded": ["5491199990000"], "included": []})
    assert await select_trigger([node], _state(contact="5491199990000")) is None


@pytest.mark.asyncio
async def test_contacto_incluido_aplica():
    node = _trigger(contact_filter={"excluded": [], "included": ["5491199990000"]})
    match = await select_trigger([node], _state(contact="5491199990000"))
    assert match is not None


@pytest.mark.asyncio
async def test_contacto_no_incluido_no_aplica():
    node = _trigger(contact_filter={"excluded": [], "included": ["5491100000001"]})
    assert await select_trigger([node], _state(contact="5491199990000")) is None


def _config_with_mass(allow: bool):
    return {
        "empresas": [{
            "id": "empresa_test",
            "name": "Empresa Test",
            "phones": [],
            "telegram": [{"token": "12345:AAA", "allow_mass": allow}],
        }],
    }


@pytest.mark.asyncio
async def test_include_all_known_con_allow_mass_y_contacto_conocido():
    node = _trigger(contact_filter={"include_all_known": True, "included": [], "excluded": []})
    with patch("config.load_config", return_value=_config_with_mass(True)), \
         patch("graphs.trigger_match._is_known_contact", new_callable=AsyncMock, return_value=True):
        match = await select_trigger([node], _state())
    assert match is not None


@pytest.mark.asyncio
async def test_include_all_known_sin_allow_mass_se_ignora():
    """Defensa en profundidad: sin allow_mass las opciones masivas no aplican."""
    node = _trigger(contact_filter={"include_all_known": True, "included": [], "excluded": []})
    with patch("config.load_config", return_value=_config_with_mass(False)), \
         patch("graphs.trigger_match._is_known_contact", new_callable=AsyncMock, return_value=True):
        match = await select_trigger([node], _state())
    assert match is None


@pytest.mark.asyncio
async def test_include_unknown_con_contacto_desconocido():
    node = _trigger(contact_filter={"include_unknown": True, "included": [], "excluded": []})
    with patch("config.load_config", return_value=_config_with_mass(True)), \
         patch("graphs.trigger_match._is_known_contact", new_callable=AsyncMock, return_value=False):
        match = await select_trigger([node], _state())
    assert match is not None


@pytest.mark.asyncio
async def test_included_por_nombre_resuelve_canales_telegram():
    """Un nombre en included se resuelve a los chat_ids de ese contacto."""
    node = _trigger(contact_filter={"excluded": [], "included": ["Juan Pérez"]})
    contacts = [{"name": "Juan Pérez", "channels": [{"type": "telegram", "value": "5491199990000"}]}]
    with patch("db.get_contacts", new_callable=AsyncMock, return_value=contacts):
        match = await select_trigger([node], _state(contact="5491199990000"))
    assert match is not None


@pytest.mark.asyncio
async def test_filtro_legacy_contact_phone_exacto():
    """Sin contact_filter cae al modo legacy: contact_phone exacto del config."""
    with _no_default_filter():
        ok = await select_trigger([_trigger(contact_phone="5491199990000")], _state())
        bad = await select_trigger([_trigger(contact_phone="5491100000001")], _state())
    assert ok is not None
    assert bad is None


# ─── Regex del mensaje ────────────────────────────────────────────────────────

def test_pattern_vacio_siempre_aplica():
    assert _matches_pattern("", "cualquier cosa")
    assert _matches_pattern("urgente", "")  # sin mensaje no se filtra


def test_pattern_matchea_case_insensitive():
    assert _matches_pattern(".*URGENTE.*", "esto es urgente!")
    assert not _matches_pattern(".*urgente.*", "todo tranquilo")


def test_pattern_invalido_no_bloquea():
    """Una regex rota no debe impedir que el flow corra (comportamiento histórico)."""
    assert _matches_pattern("[invalida(", "hola")


@pytest.mark.asyncio
async def test_select_trigger_respeta_pattern():
    with _no_default_filter():
        ok = await select_trigger(
            [_trigger(message_pattern="hola")], _state(message="hola mundo"))
        bad = await select_trigger(
            [_trigger(message_pattern="chau")], _state(message="hola mundo"))
    assert ok is not None
    assert bad is None


# ─── FlowCooldown ─────────────────────────────────────────────────────────────

def test_cooldown_inactivo_sin_marca():
    cd = FlowCooldown()
    assert not cd.is_active("f1", "c1", 4.0)


def test_cooldown_activo_tras_mark():
    cd = FlowCooldown()
    cd.mark("f1", "c1")
    assert cd.is_active("f1", "c1", 4.0)
    assert not cd.is_active("f1", "c2", 4.0), "otro contacto no se ve afectado"
    assert not cd.is_active("f2", "c1", 4.0), "otro flow no se ve afectado"


def test_cooldown_cero_horas_nunca_activo():
    cd = FlowCooldown()
    cd.mark("f1", "c1")
    assert not cd.is_active("f1", "c1", 0)


def test_cooldown_expira():
    cd = FlowCooldown()
    cd.mark("f1", "c1", when=time.time() - 5 * 3600)  # hace 5 horas
    assert not cd.is_active("f1", "c1", 4.0)
    assert cd.is_active("f1", "c1", 6.0)


def test_cooldown_has_pop_clear():
    cd = FlowCooldown()
    cd.mark("f1", "c1")
    assert cd.has("f1", "c1")
    cd.pop("f1", "c1")
    assert not cd.has("f1", "c1")
    cd.mark("f1", "c1")
    cd.clear()
    assert not cd.has("f1", "c1")


# ─── cooldown_hours: default del schema ──────────────────────────────────────

def test_cooldown_hours_explicito():
    assert cooldown_hours({"cooldown_hours": 2}, "telegram_trigger") == 2.0


def test_cooldown_hours_ausente_usa_default_del_schema():
    """Flows viejos sin el campo usan el default del schema (4h), no 0."""
    assert cooldown_hours({}, "telegram_trigger") == 4.0
    assert cooldown_hours({}, "message_trigger") == 4.0


def test_cooldown_hours_tipo_desconocido_es_cero():
    assert cooldown_hours({}, "tipo_inexistente") == 0.0
