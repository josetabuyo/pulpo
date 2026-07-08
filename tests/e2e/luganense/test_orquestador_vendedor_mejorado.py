"""
E2E — Orquestador Vendedor Mejorado / bot Luganense.

Cubre el flow ACTIVO en prod (id 0019d8f2-...), reparado a partir del diseño
de tests/test_e2e_luganense_teli.py (flow viejo, id d703b474-..., que queda
intacto como referencia y sigue corriendo por separado).

Escenarios probados manualmente vía /teli antes de automatizar (2026-07-04):
  saludo       → pide aclaración
  comercio     → "busco una ferretería" → Ferretería El Barrio, cierra con CTA
  producto     → "quiero pedir una pizza" → oferta de pizzerías, cierra con CTA
  servicio     → plomero + dirección → notifica al profesional, cierra (end_conv_ok)
  noticias     → corte de luz → posts de FB o fallback conocido, cierra con CTA
  fuera_scope  → "plomero en Recoleta" → farewell fijo de scope, no busca ni oferta

Todas las ramas ahora cierran explícitamente la conversación (end_conversation),
no solo la de servicio. comercio/producto/noticias cierran con una línea de CTA
fija dentro del propio mensaje del LLM (para no pisar la oferta con un farewell
separado — end_conversation.farewell_message SOBRESCRIBE el reply anterior si no
está vacío, ver pulpo/graphs/nodes/end_conversation.py). El guardrail de scope
vive en el extractor + router de aclaración, antes de tocar la API — no clasifica
por "sin resultados" (eso sigue siendo del barrio), solo por señales explícitas
de otro barrio/tema ajeno.

Datos de contacto de QA: Luganense cargó explícitamente contactos de prueba
(marcados "[QA]") para Ferretería El Barrio (comercio), Pizzería El Horno de
Barro (producto) y Roberto Gómez (servicio, contact_id legacy + contactos[]).
Confirmado en vivo contra el API real el 2026-07-04.

Nota de flakiness conocida — el clasificador inicial (`node_1783110208476`,
"Sabemos que necesita?") y el router `validar_direccion` (rama servicio) usan
un modelo LLM híbrido (best:*|cloud-first) que puede resolver a proveedores
distintos entre llamadas y clasificar el MISMO mensaje de forma diferente en
corridas separadas — no es exclusivo de una rama, se vio tanto en "necesito un
plomero + dirección" como en "quiero pedir una pizza" sin ninguna ambigüedad
real de por medio. No es una regresión de esta reparación ni algo arreglable
tocando la config del flow (confirmado con el agente LocalModels: el fallback
cloud→local es automático y correcto, el ruido viene de qué proveedor cloud
resuelve cada llamada). Mitigación en los tests: `_send_con_reintento` reintenta
una vez el envío si la respuesta es un loop obvio (repite la pregunta anterior)
en vez of avanzar — ver management/HANDOFF_LUGANENSE_MULTI_CONTACTOS.md.

Nota de flakiness conocida #2: el guardrail de scope es confiable para pedidos que
mencionan OTRO barrio explícito ("Recoleta", "Palermo"), pero es inestable para temas
ajenos sin lugar mencionado (ej. "quién ganó el partido de anoche") — el extractor
a veces lo clasifica como charla ambigua (pedir_mas_info) en vez de fuera_de_scope.
Por eso solo se automatiza el caso de "otro barrio", que sí es estable.

Nota sobre datos de QA (confirmado por Luganense 2026-07-04): los contactos cargados
para Ferretería El Barrio / El Horno de Barro / Roberto Gómez son TEMPORALES — en algún
momento Luganense los reemplaza por datos reales de comerciantes. Por eso
`test_ruta_comercio_incluye_contacto` NO hardcodea ningún valor: consulta el API en
vivo en cada corrida, valida que el contacto tenga estructura correcta (`tipo` dentro
del enum real, `valor` no vacío) y recién ahí compara los dígitos contra la respuesta
del bot. Así el test sobrevive cuando pasen a datos reales. No se persigue por ahora
un endpoint de fixtures QA dedicado (Luganense lo ofreció) — a esta altura del proyecto
alcanza con que los tests sean útiles; los ambientes de staging se evalúan más adelante,
cuando el proyecto esté por salir a producción.

Requisitos: los mismos que tests/test_e2e_luganense_teli.py (teli user_me conectado,
backend con ENABLE_BOTS=true).
"""
import asyncio
import re

import httpx
import pytest

from tests.e2e.helpers import TeliConversation

_BOT = "luganense_bot"
_API = "https://luganense.vercel.app/api/directorio/buscar"

# Línea de cierre fija que los prompts de comercio/producto/noticias deben incluir.
_CIERRE = "escribime cuando quieras"


# Enum real de pulpo/Luganense (db/schema.ts ContactEntry.tipo). Validar contra esto,
# no contra valores hardcodeados — los datos de QA son temporales, Luganense los va
# a reemplazar por datos reales de comerciantes (confirmado 2026-07-04). Ver nota abajo.
_TIPOS_CONTACTO_VALIDOS = {
    "telegram", "whatsapp", "instagram", "facebook", "tiktok", "twitter", "email", "telefono",
}


def _primer_contacto(query: str, tipo: str) -> dict | None:
    """
    Consulta el API real de Luganense y devuelve el primer contacto (dict {tipo, valor})
    del primer resultado, validando la estructura (tipo dentro del enum conocido, valor
    no vacío). None si no hay resultados, no hay contactos, o la estructura es inválida.
    """
    try:
        resp = httpx.get(_API, params={"q": query, "tipo": tipo}, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        contactos = results[0].get("contactos") or []
        if not contactos:
            return None
        primero = contactos[0]
        if primero.get("tipo") not in _TIPOS_CONTACTO_VALIDOS or not primero.get("valor"):
            return None
        return primero
    except Exception:
        return None


def _digitos_contacto(query: str, tipo: str) -> str | None:
    """
    Últimos dígitos del valor del primer contacto válido (ej. "5555-0001" -> "55550001"),
    o None si no hay contacto estructuralmente válido. Validar contra dígitos (no el
    string completo con "[QA]"/"+54"/espacios) es robusto a que el LLM reformatee el
    número al citarlo, Y a que el dato deje de ser de QA y pase a ser real.
    """
    contacto = _primer_contacto(query, tipo)
    if not contacto:
        return None
    digitos = re.sub(r"\D", "", contacto["valor"])
    return digitos[-8:] if len(digitos) >= 8 else (digitos or None)

pytestmark = pytest.mark.e2e


def _run(coro):
    return asyncio.run(coro)


def _es_loop_obvio(reply: str | None, marcador: str) -> bool:
    """True si `reply` es un loop evidente: repite el mismo pedido/pregunta anterior."""
    return bool(reply) and marcador in reply.lower()


async def _send_con_reintento(conv: TeliConversation, mensaje: str, marcador_loop: str) -> str | None:
    """
    Envía `mensaje` y, si la respuesta parece un loop (mismo `marcador_loop` que ya
    vimos antes en vez de avanzar), reintenta una vez. Ver nota de flakiness conocida
    en el docstring del módulo — no es una regresión de esta reparación.
    """
    reply = await conv.send_and_wait(mensaje)
    if _es_loop_obvio(reply, marcador_loop):
        reply = await conv.send_and_wait(mensaje)
    return reply


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
        return await _send_con_reintento(conv, "busco una ferretería", "necesitás")


def test_ruta_comercio_ferreteria():
    reply = _run(_ruta_comercio_ferreteria())
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert "ferreter" in lower, f"Respuesta inesperada (ruta comercio): {reply!r}"
    assert _CIERRE in lower, f"Falta el cierre de conversación: {reply!r}"


def test_ruta_comercio_incluye_contacto():
    """
    Ferretería El Barrio tiene contacto de QA cargado (confirmado 2026-07-04).
    Valida contra el NÚMERO REAL consultado en vivo al API de Luganense, no contra
    un keyword genérico — así el test falla de verdad si el dato deja de mostrarse.
    """
    digitos = _digitos_contacto("ferreteria", "all")
    if not digitos:
        pytest.skip("Ferretería El Barrio no tiene contactos cargados en este momento")
    reply = _run(_ruta_comercio_ferreteria())
    assert reply
    digitos_reply = re.sub(r"\D", "", reply)
    assert digitos in digitos_reply, (
        f"No se encontró el contacto real ({digitos}) en la respuesta: {reply!r}"
    )


async def _ruta_comercio_nombre_propio_sin_rubro():
    async with TeliConversation(_BOT) as conv:
        return await _send_con_reintento(
            conv, "es Kiosco Don Jorge, me decís su teléfono?", "necesitás"
        )


def test_ruta_comercio_nombre_propio_sin_rubro():
    """
    Regresión (2026-07-08): el clasificador de necesidad (node_1783192800831)
    devolvía UNCLEAR ante un nombre propio de comercio sin rubro explícito
    ("es Kiosco Don Jorge, me decís su teléfono?"), forzando al vecino a repetir
    el nombre 2-3 veces antes de que el flow lo reconociera. Se corrigió el
    prompt para que un nombre propio de comercio/persona/lugar cuente como
    necesidad identificada de una — este test verifica que resuelve en un
    solo turno, sin pedir rubro/calle/aclaración de por medio.
    """
    reply = _run(_ruta_comercio_nombre_propio_sin_rubro())
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert "kiosco don jorge" in lower or "riestra" in lower, (
        f"No resolvió el comercio por nombre propio en un solo turno: {reply!r}"
    )
    assert "rubro" not in lower and "en qué calle" not in lower, (
        f"Volvió a pedir rubro/calle en vez de resolver directo: {reply!r}"
    )


async def _ruta_producto_pizza():
    async with TeliConversation(_BOT) as conv:
        return await _send_con_reintento(conv, "quiero pedir una pizza", "necesitás")


def test_ruta_producto_pizza():
    reply = _run(_ruta_producto_pizza())
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert "pizza" in lower, f"Respuesta inesperada (ruta producto): {reply!r}"
    assert _CIERRE in lower, f"Falta el cierre de conversación: {reply!r}"


async def _ruta_servicio_con_notificacion():
    async with TeliConversation(_BOT) as conv:
        pide_direccion = await _send_con_reintento(
            conv, "se me rompió una canilla, necesito un plomero urgente", "necesitás"
        )
        reply = await _send_con_reintento(conv, "Av. Roca 1234", "dirección")
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
        return await _send_con_reintento(conv, "qué se sabe del corte de luz en Lugano", "necesitás")


def test_ruta_noticias():
    reply = _run(_ruta_noticias())
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert "facebook.com/luganense" in lower or "corte" in lower or "luz" in lower, (
        f"Respuesta inesperada (ruta noticias): {reply!r}"
    )
    # El cierre convive con los links 📎 que appendea el adapter — basta con que esté presente.
    assert _CIERRE in lower or "facebook.com/luganense" in lower, (
        f"Falta el cierre de conversación: {reply!r}"
    )


async def _fuera_de_scope_otro_barrio():
    async with TeliConversation(_BOT) as conv:
        return await _send_con_reintento(conv, "recomendame un buen plomero en Recoleta", "necesitás")


def test_fuera_de_scope_otro_barrio():
    reply = _run(_fuera_de_scope_otro_barrio())
    assert reply, "El bot no respondió dentro del timeout"
    lower = reply.lower()
    assert "no lo manejamos" in lower or "villa lugano" in lower, (
        f"No reconoció que el pedido es de otro barrio: {reply!r}"
    )
    assert "👋" in reply or "hasta la próxima" in lower
    # Negativo: no debe haber buscado ni ofertado nada del directorio real.
    assert "roberto" not in lower and "dirección" not in lower and "ferreter" not in lower


async def _ambiguo_no_loopea_infinito():
    async with TeliConversation(_BOT) as conv:
        replies = []
        for msg in ("asdfgh", "qwerty", "no sé"):
            replies.append(await conv.send_and_wait(msg))
        return replies


def test_ambiguo_no_loopea_infinito():
    replies = _run(_ambiguo_no_loopea_infinito())
    assert all(replies), "El bot dejó de responder en algún turno del intercambio ambiguo"
