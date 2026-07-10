"""
E2E — smoke de conectividad Telegram / bot Luganense.

Único test de todo `tests/e2e/luganense/` que sigue hablando con Telegram
real (`@luganense_bot` vía `TeliConversation`, Telethon con la sesión
`user_me`). Toda la lógica de negocio (rutas de comercio, producto, servicio,
noticias, fuera de scope, agotamiento) se movió al simulador in-band — ver
`scenarios.py` (fuente única, también usada por
`scripts/generate_e2e_report.py`) y `test_orquestador_vendedor_sim.py`
(marker `e2e_sim`).

Este test solo confirma que el bot está vivo y responde por Telegram: "hola"
→ alguna respuesta. Requiere `ENABLE_BOTS=true` en el backend + sesión
`teli user_me` conectada (ver docs/adr/004-estrategia-de-tests.md, Capa 3).
Correrlo manda un mensaje real al bot de producción — no automatizar en CI.
"""
import asyncio

import pytest

from tests.e2e.helpers import TeliConversation

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
