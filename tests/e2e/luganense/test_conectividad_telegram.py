"""
E2E — smoke de conectividad Telegram / bot Luganense.

Único test de todo `tests/e2e/luganense/` que sigue hablando con Telegram
real (`@luganense_bot` vía `TeliConversation`, Telethon con la sesión
`user_me`). Toda la lógica de negocio (rutas de comercio, producto, servicio,
noticias, fuera de scope, agotamiento) se movió al simulador in-band — ver
`scenarios.py` (fuente única, también usada por
`scripts/generate_e2e_report.py`) y `test_orquestador_vendedor_sim.py`
(marker `e2e_sim`).

`test_conectividad_hola_responde` solo confirma que el bot está vivo y
responde por Telegram: "hola" → alguna respuesta.

`test_conectividad_comercio_no_se_trunca` valida contra el bot REAL (no el
simulador) que el reply del nodo "Armar mensaje referencia de comercio" sale
completo — bug real encontrado el 2026-07-12 (el nodo no tenía `max_tokens`
configurado, el default del proveedor cortaba la respuesta a mitad de frase
cuando había 2+ comercios con todos sus datos de contacto). El simulador
in-band ya lo cubre (`scenarios.py::_run_comercio`), pero corriéndolo también
acá queda auditable de verdad en el historial de Telegram, no solo en el
reporte HTML.

Requiere `ENABLE_BOTS=true` en el backend + sesión `teli user_me` conectada
(ver docs/adr/004-estrategia-de-tests.md, Capa 3). Correrlo manda mensajes
reales al bot de producción — no automatizar en CI.
"""
import asyncio

import pytest

from tests.e2e.helpers import TeliConversation
from tests.e2e.luganense.scenarios import CIERRE

_BOT = "luganense_bot"

pytestmark = pytest.mark.e2e


def _run(coro):
    return asyncio.run(coro)


async def _hola_responde():
    async with TeliConversation(_BOT) as conv:
        return await conv.send_and_wait("hola")


def test_conectividad_hola_responde():
    reply = _run(_hola_responde())
    assert reply, "El bot no respondió dentro del timeout — revisar ENABLE_BOTS/teli"


async def _busco_ferreteria():
    async with TeliConversation(_BOT) as conv:
        return await conv.send_and_wait("busco una ferretería")


def test_conectividad_comercio_no_se_trunca():
    reply = _run(_busco_ferreteria())
    assert reply, "El bot no respondió dentro del timeout — revisar ENABLE_BOTS/teli"
    lower = reply.lower()
    assert "ferreter" in lower, f"La respuesta no menciona la ferretería: {reply!r}"
    assert CIERRE in lower, (
        f"La respuesta no incluye la línea de cierre completa — sospecha de "
        f"truncado por max_tokens: {reply!r}"
    )
