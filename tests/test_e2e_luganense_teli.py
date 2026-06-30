"""
E2E tests — Orquestador Vendedor / bot Luganense, 4 rutas.

Estrategia de polling (settle-time):
  1. Enviamos el mensaje y registramos my_msg_id.
  2. Polling de get_messages(min_id=my_msg_id) buscando replies del bot.
  3. Tras el primer reply esperamos SETTLE_TIME s para capturar replies de cola
     pendiente. Devolvemos el ÚLTIMO reply (siempre es el nuestro — FIFO).

Caminos probados y datos conocidos del ambiente:
  servicio   → buscar_oficio (Servicios sheet)
               electricista → Gregorio (GM Electricidad)
               plomero      → Roberto Gómez
  producto   → buscar_auspiciante (Productos sheet) + pre_route_rule
               pizza        → La Esquina de Lugano Pizza  📦 1158920034
               carnicería   → Carnicería El Corte Fino     📞 1144230078
  directorio → buscar_directorio (luganense.vercel.app/api/directorio)
               ferretería   → Ferretería El Barrio (Av. Lugano 1234, 011-4601-1234)
  noticias   → expandir_consulta + buscar_posts_fb (Facebook)
               Si FB activo: contenido de posts recientes del barrio.
               Si FB inactivo: "no encontré publicaciones ... facebook.com/luganense"

Requisitos:
  - `teli user connect` hecho al menos una vez (sesión me activa)
  - Backend Luganense corriendo en producción con FB cookies activas
  - Ejecutar con: pytest -m e2e tests/test_e2e_luganense_teli.py -v
"""
import asyncio
import time
from pathlib import Path

import pytest

# ─── Config ───────────────────────────────────────────────────────────────────

_TELI_DATA = Path("/Users/josetabuyo/Development/teli/data")
_SESSION   = str(_TELI_DATA / "sessions" / "user_me")
_API_ID    = 31604778
_API_HASH  = "385bf75876904b022cb411c1c1954088"
_BOT       = "luganense_bot"

TIMEOUT     = 180  # 3 min: cola del bot + procesamiento
SETTLE_TIME = 15   # s de silencio post primer reply antes de retornar

pytestmark = pytest.mark.e2e


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _send_and_receive(message: str, timeout: int) -> str:
    """
    Envía `message` al bot y devuelve el ÚLTIMO reply del bot dentro del timeout.

    Estrategia "settle": tras el primer reply, espera SETTLE_TIME s por posibles
    replies de cola de mensajes anteriores. El último siempre es el nuestro (FIFO).
    """
    from telethon import TelegramClient

    client = TelegramClient(_SESSION, _API_ID, _API_HASH)
    await client.start()

    bot_entity = await client.get_entity(_BOT)
    bot_id = bot_entity.id

    sent = await client.send_message(_BOT, message)
    my_msg_id = sent.id

    collected: list[str] = []
    last_seen_id = my_msg_id
    first_reply_at: float | None = None
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        await asyncio.sleep(5)
        new_msgs = await client.get_messages(bot_entity, limit=30, min_id=last_seen_id)
        fresh = [m for m in sorted(new_msgs, key=lambda m: m.id)
                 if m.sender_id == bot_id and m.text]
        for m in fresh:
            collected.append(m.text)
            last_seen_id = m.id
        if fresh and first_reply_at is None:
            first_reply_at = time.monotonic()
        if first_reply_at is not None and time.monotonic() >= first_reply_at + SETTLE_TIME:
            break

    await client.disconnect()
    return collected[-1] if collected else ""


def send_and_receive(message: str, timeout: int = TIMEOUT) -> str:
    return asyncio.run(_send_and_receive(message, timeout))


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_ruta_servicio():
    """
    Camino feliz — ruta servicio.
    El bot consulta la API de Luganense (tipo=servicios), encuentra a Gregorio
    (GM Electricidad) y confirma al vecino con nombre y zona de cobertura.
    contact_id=null por ahora → notificación al trabajador no llega, pero la
    respuesta al vecino sí debe mencionar al proveedor encontrado.
    """
    reply = send_and_receive("Necesito un electricista urgente por favor")
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert any(kw in lower for kw in (
        "electricista", "electricidad", "gregorio", "lugano", "barrio"
    )), f"Respuesta inesperada (ruta servicio): {reply!r}"


def test_ruta_producto():
    """
    Camino feliz — ruta producto.
    El bot consulta la API de Luganense (tipo=all → _tipo=producto) y presenta
    opciones de pizza con delivery. La API puede devolver varios resultados
    (La Esquina, Chicken House, El Horno de Barro, etc.).
    """
    reply = send_and_receive("¿Dónde puedo pedir una pizza con delivery?")
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    # El bot debe mencionar al menos un negocio (no el fallback genérico)
    assert "¡contame qué necesitás" not in lower, \
        f"El bot respondió el fallback genérico en vez del negocio: {reply!r}"
    assert any(kw in lower for kw in (
        "pizza", "delivery", "lugano", "esquina", "empanada"
    )), f"Respuesta inesperada (ruta producto): {reply!r}"


def test_ruta_directorio():
    """
    Camino feliz — ruta directorio.
    El bot consulta la API de Luganense (tipo=all → _tipo=comercio), encuentra
    Ferretería El Barrio (Av. Lugano 1234, 011-4601-1234) y la presenta.
    """
    reply = send_and_receive("¿Hay una ferretería cerca del barrio?")
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert any(kw in lower for kw in (
        "ferreter", "lugano", "1234", "herramientas", "materiales"
    )), f"Respuesta inesperada (ruta directorio): {reply!r}"
    assert "no encontré" not in lower, \
        f"El bot respondió que no encontró nada: {reply!r}"


def test_ruta_noticias():
    """
    Camino feliz — ruta noticias.
    El bot busca posts relevantes en Facebook de Luganense y responde con
    contenido del barrio. Si FB no está activo devuelve el link oficial.
    En ambos casos la respuesta debe ser sobre Villa Lugano.
    """
    reply = send_and_receive("¿Qué pasó en el barrio esta semana?")
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    # Con FB activo: responde con contenido real del barrio
    # Sin FB activo: responde "no encontré publicaciones" + link a facebook.com/luganense
    assert any(kw in lower for kw in (
        "lugano", "barrio", "facebook", "publicaciones", "vecino", "semana"
    )), f"Respuesta inesperada (ruta noticias): {reply!r}"
    # No debe ser una respuesta de servicio/trabajador
    assert "te va a contactar" not in lower, \
        f"El bot respondió como ruta servicio en vez de noticias: {reply!r}"
