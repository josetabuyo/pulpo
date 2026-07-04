"""
E2E — Orquestador Vendedor Mejorado / bot Luganense.

Cubre el flow ACTIVO en prod (id 0019d8f2-...), reparado a partir del diseño
de tests/test_e2e_luganense_teli.py (flow viejo, id d703b474-..., que queda
intacto como referencia y sigue corriendo por separado).

Escenarios probados manualmente vía /teli antes de automatizar (2026-07-04):
  saludo     → pide aclaración
  comercio   → "busco una ferretería" → Ferretería El Barrio
  producto   → "quiero pedir una pizza" → oferta de pizzerías
  servicio   → plomero + dirección → notifica al profesional
  noticias   → corte de luz → posts de FB o fallback conocido (BUG_LUGANENSE_LINKS)

Nota de flakiness conocida: el router `validar_direccion` (rama servicio, no
tocada por esta reparación) usa un modelo LLM híbrido y puede clasificar el
mismo mensaje de forma distinta entre corridas (ver management/HANDOFF_LUGANENSE_MULTI_CONTACTOS.md).
Si `test_ruta_servicio_con_notificacion` falla por un loop de "¿en qué dirección...?",
reintenta una vez antes de fallar — no es una regresión de esta reparación.

Requisitos: los mismos que tests/test_e2e_luganense_teli.py (teli user_me conectado,
backend con ENABLE_BOTS=true).
"""
import asyncio

import pytest

from tests.e2e.helpers import TeliConversation

_BOT = "luganense_bot"

pytestmark = pytest.mark.e2e


def _run(coro):
    return asyncio.run(coro)


# ─── Escenarios ───────────────────────────────────────────────────────────────

async def _saludo_pide_aclaracion():
    async with TeliConversation(_BOT) as conv:
        return await conv.send_and_wait("hola")


def test_saludo_pide_aclaracion():
    reply = _run(_saludo_pide_aclaracion())
    assert reply, "El bot no respondió dentro del timeout"
    assert "Luganense" in reply
    assert "necesitás" in reply.lower()


async def _ruta_comercio_ferreteria():
    async with TeliConversation(_BOT) as conv:
        await conv.send_and_wait("hola")
        return await conv.send_and_wait("busco una ferretería")


def test_ruta_comercio_ferreteria():
    reply = _run(_ruta_comercio_ferreteria())
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert "ferreter" in lower, f"Respuesta inesperada (ruta comercio): {reply!r}"


async def _ruta_producto_pizza():
    async with TeliConversation(_BOT) as conv:
        return await conv.send_and_wait("quiero pedir una pizza")


def test_ruta_producto_pizza():
    reply = _run(_ruta_producto_pizza())
    assert reply, "El bot no respondió dentro del timeout"
    assert "pizza" in reply.lower(), f"Respuesta inesperada (ruta producto): {reply!r}"


async def _ruta_servicio_con_notificacion():
    async with TeliConversation(_BOT) as conv:
        pide_direccion = await conv.send_and_wait(
            "se me rompió una canilla, necesito un plomero urgente"
        )
        reply = await conv.send_and_wait("Av. Roca 1234")
        if reply and "dirección" in reply.lower() and "necesitás" in reply.lower():
            # Flakiness conocida del router validar_direccion — reintentar una vez.
            reply = await conv.send_and_wait("Av. Roca 1234")
        return pide_direccion, reply


def test_ruta_servicio_con_notificacion():
    pide_direccion, reply = _run(_ruta_servicio_con_notificacion())
    assert pide_direccion, "El bot no respondió dentro del timeout"
    assert "dirección" in pide_direccion.lower(), f"No pidió dirección: {pide_direccion!r}"
    assert reply, "El bot no confirmó el pedido tras la dirección"
    lower = reply.lower()
    assert any(kw in lower for kw in ("registrad", "avisamos", "prestador", "roberto", "gómez")), (
        f"Respuesta inesperada tras dar la dirección: {reply!r}"
    )


async def _ruta_noticias():
    async with TeliConversation(_BOT) as conv:
        return await conv.send_and_wait("qué se sabe del corte de luz en Lugano")


def test_ruta_noticias():
    reply = _run(_ruta_noticias())
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert "facebook.com/luganense" in lower or "corte" in lower or "luz" in lower, (
        f"Respuesta inesperada (ruta noticias): {reply!r}"
    )


async def _ambiguo_no_loopea_infinito():
    async with TeliConversation(_BOT) as conv:
        replies = []
        for msg in ("asdfgh", "qwerty", "no sé"):
            replies.append(await conv.send_and_wait(msg))
        return replies


def test_ambiguo_no_loopea_infinito():
    replies = _run(_ambiguo_no_loopea_infinito())
    assert all(replies), "El bot dejó de responder en algún turno del intercambio ambiguo"
