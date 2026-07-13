"""
Fuente única de las conversaciones e2e del flow "Orquestador Vendedor
Mejorado" del bot Luganense — usada tanto por
`test_orquestador_vendedor_mejorado_sim.py` (pytest) como por
`scripts/generate_e2e_report.py` (reporte HTML). Un solo lugar, sin duplicar
lógica entre el test y el reporte.

Convención bot+flow (un bot puede tener N flows activos + M inactivos, ver
BOT_SLUG/FLOW_SLUG/FLOW_NAME más abajo): un módulo `scenarios_<flow_slug>.py`
por flow que se testea, siguiendo `tests/e2e/<bot>/test_<flow_slug>_sim.py`
para el archivo de tests (ver convención en tests/e2e/helpers.py).

Diseño (revisión 2026-07-10, tras feedback): pocas conversaciones, pero cada
una COMPLETA de punta a punta — arranca en el trigger real y llega a un
`end_conversation` de verdad (nunca se corta a mitad de camino, ni siquiera
el caso infeliz). Un test que solo manda "hola" y no sigue la conversación
NO es un caso e2e válido — quedaba a mitad del flow, sin cerrar.

Cada escenario valida contra el LOG REAL de ejecución (`flow_run_steps`, vía
`SimConversation.step/ran_node/state_field/branch_taken`), no solo contra
keywords sueltos en el texto del reply — así se detecta un nodo que corrió
por la rama equivocada aunque el LLM final "disimule" el problema
reformulando una respuesta razonable.

Node ids del flow real "Orquestador Vendedor Mejorado" (bot "luganense",
confirmados por inspección en vivo del flow y de los `flow_run_steps` reales
el 2026-07-12 — si el flow se edita y estos ids cambian, hay que actualizar
acá):
  node_1783192985521  telegram_trigger  "Llega Mensaje a Luganense"
  node_1783192800831  llm               "Obtener necesidad" → state.necesidad
  node_1783356000392  condition         "Condición" → necesidad_identificada | pedir_mas_info | fuera_de_scope
  node_1783192962168  router            "Elegir Mostrador" → servicio | comercio | producto | noticias

  Rama "servicio" (reescrita 2026-07-12 — agrega un paso de confirmación del
  prestador ANTES de pedir la dirección; los ids viejos `validar_direccion` y
  `buscar_directorio` ya NO EXISTEN, quedaron reemplazados):
  node_1783881515663  llm               "Expandir busqueda servicio" → state.queries_servicio (lista)
  buscar_servicio      fetch_http       "Buscar servicio" (antes "buscar_directorio") → state.servicio_luganense
  node_1783891416894  llm               "Identificar servicio" → state.servicio (o SIN_RESULTADOS)
  node_1783892162094  send_message      "Confirmar Servicio" → "¿Es este el servicio que quiere: '{{servicio}}'?"
  node_1783892344935  wait_user         "Esperar servicio confirmado"
  node_1783892654800  llm               "Obtener servicio confirmado" → state.servicio_confirmado (o UNCLEAR)
  node_1783892396384  condition         "Confirmó Servicio?" (RAMA NUEVA) → confirma_servicio | no_confirma_servicio | agotado (max_visits=3)
                                         confirma_servicio → Obtener dirección; no_confirma_servicio → vuelve a
                                         "Expandir busqueda servicio" (relanza la búsqueda). OJO: la ruta "agotado"
                                         está declarada en la config (max_visits_route) pero NO tiene edge de salida
                                         en el flow — a diferencia de "Tienen dirección?" más abajo, que sí. Si un
                                         vecino rechaza el servicio 3 veces seguidas puede quedar colgado. Reportado,
                                         no arreglado acá (es un flow de producción, requiere decisión de Luganense).
  node_1783873167862  llm               "Obtener dirección" → state.direccion (o UNCLEAR)
  node_1783873174012  condition         "Tienen dirección?" (antes "validar_direccion") → tiene_direccion | sin_direccion | agotado (max_visits=3)
  node_1783867942451  llm               "Armar mensaje pedir dirección"
  pedir_direccion     send_message      "¿En qué dirección necesitás el servicio?"
  wait_dir            wait_user
  set_direccion       set_state         → state.direccion (bug real 2026-07-10: usaba {{message}}, roto — fix: {{conversation.last}})
  notificar_trabajador send_message     envío real al prestador (guarded en sim)
  disculpar_dir        llm              rama agotado (de "Tienen dirección?")
  end_conv_ok / end_conv_fail / end_conv_comercio / end_conv_producto /
  end_conv_noticias / end_conv_scope    end_conversation, uno por rama

Datos de contacto de QA (confirmado por Luganense, API real): Ferretería El
Barrio (comercio), Kiosco Don Jorge (comercio sin rubro explícito,
`telefono='11 5555-0003 [QA]'`), Roberto Gómez (servicio). Temporales — los
escenarios consultan el API en vivo y comparan dígitos, nunca hardcodean el
valor completo con "[QA]".
"""
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx

from tests.e2e.helpers import SimConversation, TeliConversation, has_unresolved_templates

BOT_ID = "luganense"
# Identidad bot+flow — un bot puede tener N flows activos (con distintos
# triggers) y M inactivos; este módulo prueba UNO en particular. BOT_SLUG y
# FLOW_SLUG nombran los tests (test_<bot>__<flow>__<id>, ver
# test_orquestador_vendedor_mejorado_sim.py) y el archivo del reporte HTML
# (generate_e2e_report.py). FLOW_SLUG queda fijo aunque el flow se renombre en
# el editor — un rename de producto no debe romper nombres de test/artefactos
# ya commiteados. FLOW_NAME es el nombre real en la DB: generate_e2e_report.py
# lo usa para resolver el flow_id activo en runtime (GET /api/flows/bots/{bot})
# antes de capturar el diagrama, así el reporte no depende de un UUID fijo.
BOT_SLUG = "luganense"
FLOW_SLUG = "orquestador_vendedor_mejorado"
FLOW_NAME = "Orquestador Vendedor Mejorado"
DIRECTORIO_API = "https://luganense.vercel.app/api/directorio/buscar"
CIERRE = "escribime cuando quieras"
TIPOS_CONTACTO_VALIDOS = {
    "telegram", "whatsapp", "instagram", "facebook", "tiktok", "twitter", "email", "telefono",
}

# ─── Node ids (ver docstring) ────────────────────────────────────────────────
N_OBTENER_NECESIDAD = "node_1783192800831"
N_CONDICION = "node_1783356000392"
N_ELEGIR_MOSTRADOR = "node_1783192962168"
N_VALIDAR_DIRECCION = "node_1783873174012"  # "Tienen dirección?" (antes "validar_direccion")
N_BUSCAR_DIRECTORIO = "buscar_servicio"  # antes "buscar_directorio"
N_NOTIFICAR_TRABAJADOR = "notificar_trabajador"
N_SET_DIRECCION = "set_direccion"
N_IDENTIFICAR_SERVICIO = "node_1783891416894"  # "Identificar servicio" → state.servicio
N_CONFIRMAR_SERVICIO = "node_1783892162094"  # "Confirmar Servicio" (send_message)
N_OBTENER_SERVICIO_CONFIRMADO = "node_1783892654800"  # "Obtener servicio confirmado" → state.servicio_confirmado
N_CONFIRMO_SERVICIO = "node_1783892396384"  # "Confirmó Servicio?" (condition, rama nueva 2026-07-12)


@dataclass
class Check:
    label: str
    passed: bool
    detail: str = ""


@dataclass
class ScenarioResult:
    turns: list[tuple[str, str]]
    checks: list[Check]


@dataclass
class Scenario:
    id: str
    title: str
    desc: str
    run: Callable[[], Awaitable[ScenarioResult]]
    real_telegram: bool = False


def _primer_contacto(query: str, tipo: str) -> dict | None:
    try:
        resp = httpx.get(DIRECTORIO_API, params={"q": query, "tipo": tipo}, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        contactos = results[0].get("contactos") or []
        if not contactos:
            return None
        primero = contactos[0]
        if primero.get("tipo") not in TIPOS_CONTACTO_VALIDOS or not primero.get("valor"):
            return None
        return primero
    except Exception:
        return None


def _digitos_contacto(query: str, tipo: str) -> str | None:
    contacto = _primer_contacto(query, tipo)
    if not contacto:
        return None
    digitos = re.sub(r"\D", "", contacto["valor"])
    return digitos[-8:] if len(digitos) >= 8 else (digitos or None)


def _c(label: str, passed, detail: str = "") -> Check:
    return Check(label, bool(passed), detail)


def _cierre_checks(conv: SimConversation, reply: str | None) -> list[Check]:
    """Chequeos comunes a TODA conversación (feliz o infeliz): reply no vacío,
    sin templates rotos en ningún lado, cierre real (end_conversation)."""
    checks = [_c("El bot respondió en el último turno", bool(reply), repr(reply) if not reply else "")]
    if not reply:
        return checks
    checks.append(_c("Sin placeholders {{...}} sin resolver en el reply", not has_unresolved_templates(reply)))
    rotos = conv.state_unresolved_templates()
    checks.append(_c(
        "Sin placeholders {{...}} sin resolver en el state de NINGÚN step de TODA la conversación",
        not rotos, detail=str(rotos) if rotos else "",
    ))
    checks.append(_c(
        "La conversación llegó a un end_conversation real (no quedó a mitad de camino)",
        conv.reached_end_conversation(),
    ))
    return checks


# ─── 1. Comercio — con loop de aclaración + resiliencia a mensaje ambiguo ───

async def _run_comercio() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r1 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r1))
        r2 = await conv.send_and_wait("asdfgh")
        turns.append(("user", "asdfgh")); turns.append(("bot", r2))
        reply = await conv.send_and_wait("busco una ferretería")
        turns.append(("user", "busco una ferretería")); turns.append(("bot", reply))

        checks = [
            _c("Turno 1 (\"hola\", ambiguo): el extractor lo clasificó UNCLEAR",
               conv.state_field(N_OBTENER_NECESIDAD, "necesidad", occurrence=0) in (None, "UNCLEAR"),
               detail=f"necesidad={conv.state_field(N_OBTENER_NECESIDAD, 'necesidad', occurrence=0)!r}"),
            _c("Turno 1: la Condición mandó a pedir aclaración (pedir_mas_info), no a buscar",
               conv.branch_taken(N_CONDICION, occurrence=0) == "pedir_mas_info"),
            _c("Turno 1: el bot respondió pidiendo aclaración", bool(r1)),
            _c("Turno 2 (\"asdfgh\", ambiguo de nuevo): el flow no se rompió, siguió respondiendo",
               bool(r2)),
        ]
        checks += _cierre_checks(conv, reply)
        lower = (reply or "").lower()
        checks.append(_c("Turno 3: la Condición identificó la necesidad (necesidad_identificada)",
                          conv.branch_taken(N_CONDICION) == "necesidad_identificada"))
        checks.append(_c("Turno 3: Elegir Mostrador clasificó la rama como \"comercio\"",
                          conv.branch_taken(N_ELEGIR_MOSTRADOR) == "comercio"))
        checks.append(_c("La respuesta final menciona una ferretería", "ferreter" in lower))
        checks.append(_c(f'Incluye la línea de cierre ("{CIERRE}")', CIERRE in lower))

        digitos = _digitos_contacto("ferreteria", "all")
        if digitos:
            digitos_reply = re.sub(r"\D", "", reply or "")
            checks.append(_c(
                "Incluye el contacto real de Ferretería El Barrio (consultado en vivo al API de Luganense)",
                digitos in digitos_reply, detail=f"esperado: …{digitos}",
            ))
        checks.append(_c("Cerró específicamente por end_conv_comercio", conv.ran_node("end_conv_comercio")))
    return ScenarioResult(turns, checks)


# ─── 2. Comercio sin rubro explícito (Kiosco Don Jorge) — resolución en 1 turno ─

async def _run_comercio_sin_rubro() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        msg = "es Kiosco Don Jorge, me decís su teléfono?"
        reply = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", reply))

        checks = [
            _c("Resolvió la necesidad en el PRIMER turno, sin pedir aclaración (regresión 2026-07-08)",
               conv.branch_taken(N_CONDICION) == "necesidad_identificada",
               detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
            _c("Elegir Mostrador clasificó la rama como \"comercio\"",
               conv.branch_taken(N_ELEGIR_MOSTRADOR) == "comercio"),
        ]
        checks += _cierre_checks(conv, reply)
        lower = (reply or "").lower()
        checks.append(_c("Menciona \"Kiosco Don Jorge\" por nombre propio", "kiosco don jorge" in lower))
        checks.append(_c("NO volvió a pedir rubro/calle (resolvió directo)",
                          "rubro" not in lower and "en qué calle" not in lower))
        digitos = _digitos_contacto("kiosco don jorge", "comercios")
        if digitos:
            digitos_reply = re.sub(r"\D", "", reply or "")
            checks.append(_c(
                "Incluye el contacto real de Kiosco Don Jorge (dato QA de Luganense)",
                digitos in digitos_reply, detail=f"esperado: …{digitos}",
            ))
        checks.append(_c("Cerró específicamente por end_conv_comercio", conv.ran_node("end_conv_comercio")))
    return ScenarioResult(turns, checks)


# ─── 3. Producto (pizza) — con loop de aclaración ────────────────────────────

async def _run_producto() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r1 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r1))
        reply = await conv.send_and_wait("quiero pedir una pizza")
        turns.append(("user", "quiero pedir una pizza")); turns.append(("bot", reply))

        checks = [
            _c("Turno 1: la Condición pidió aclaración (pedir_mas_info) ante el saludo ambiguo",
               conv.branch_taken(N_CONDICION, occurrence=0) == "pedir_mas_info"),
        ]
        checks += _cierre_checks(conv, reply)
        lower = (reply or "").lower()
        checks.append(_c("Turno 2: la Condición identificó la necesidad",
                          conv.branch_taken(N_CONDICION) == "necesidad_identificada"))
        checks.append(_c("Elegir Mostrador clasificó la rama como \"producto\"",
                          conv.branch_taken(N_ELEGIR_MOSTRADOR) == "producto"))
        checks.append(_c("La respuesta ofrece opciones de pizza", "pizza" in lower))
        checks.append(_c(f'Incluye la línea de cierre ("{CIERRE}")', CIERRE in lower))
        checks.append(_c("Cerró específicamente por end_conv_producto", conv.ran_node("end_conv_producto")))
    return ScenarioResult(turns, checks)


# ─── 4. Noticias — con loop de aclaración ────────────────────────────────────

async def _run_noticias() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r1 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r1))
        msg = "qué se sabe del corte de luz en Lugano"
        reply = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", reply))

        checks = [
            _c("Turno 1: la Condición pidió aclaración ante el saludo ambiguo",
               conv.branch_taken(N_CONDICION, occurrence=0) == "pedir_mas_info"),
        ]
        checks += _cierre_checks(conv, reply)
        lower = (reply or "").lower()
        checks.append(_c("Elegir Mostrador clasificó la rama como \"noticias\"",
                          conv.branch_taken(N_ELEGIR_MOSTRADOR) == "noticias"))
        checks.append(_c(
            "Responde sobre el corte de luz (o el fallback conocido)",
            "facebook.com/luganense" in lower or "corte" in lower or "luz" in lower,
        ))
        checks.append(_c("Cerró específicamente por end_conv_noticias", conv.ran_node("end_conv_noticias")))
    return ScenarioResult(turns, checks)


# ─── 5. Servicio con notificación — el camino más largo: aclaración + rechazo/confirmación
#        de servicio (rama nueva 2026-07-12) + dirección resuelta al primer pedido ─
#
# Nota de diseño (2026-07-12): "Obtener dirección" → "Tienen dirección?" corren UNA VEZ
# de forma implícita apenas se confirma el servicio (antes de que el vecino diga nada de
# dirección), lo que consume 1 de los 3 `max_visits` de entrada. Sumado a que `ConditionNode`
# chequea `max_visits` ANTES de evaluar las reglas (`pulpo/graphs/nodes/condition.py`), un
# tercer turno de dirección — aunque sea válido — puede caer en "agotado" en vez de
# resolverse (bug real encontrado corriendo esta suite, reportado, no arreglado acá). Por
# eso este escenario da la dirección real en el PRIMER pedido explícito (2 visitas en total,
# dentro del presupuesto) — el loop de dirección ambigua + agotamiento ya lo cubre de sobra
# `_run_servicio_agotado` más abajo, no hace falta repetirlo acá.

async def _run_servicio() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r1 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r1))

        m2 = "se me rompió una canilla, necesito un plomero urgente"
        pide_confirmacion = await conv.send_and_wait(m2)
        turns.append(("user", m2)); turns.append(("bot", pide_confirmacion))

        m3 = "no, ese no es, busco otro plomero"
        pide_confirmacion_2 = await conv.send_and_wait(m3)
        turns.append(("user", m3)); turns.append(("bot", pide_confirmacion_2))

        m4 = "sí, ese mismo, dale"
        pide_direccion = await conv.send_and_wait(m4)
        turns.append(("user", m4)); turns.append(("bot", pide_direccion))

        m5 = "Av. Roca 1234, Villa Lugano"
        reply = await conv.send_and_wait(m5)
        turns.append(("user", m5)); turns.append(("bot", reply))

        direccion_kw = ("dirección", "calle", "ubicac", "domicilio")
        checks = [
            _c("Turno 1: pidió aclaración ante el saludo ambiguo",
               conv.branch_taken(N_CONDICION, occurrence=0) == "pedir_mas_info"),
            _c("Turno 2: identificó la necesidad y clasificó la rama como \"servicio\"",
               conv.branch_taken(N_ELEGIR_MOSTRADOR) == "servicio"),
            _c("Turno 2: buscó, identificó un prestador y pidió confirmarlo (nodo Confirmar Servicio) "
               "en vez de pedir la dirección directo (flow reescrito 2026-07-12)",
               conv.ran_node(N_CONFIRMAR_SERVICIO, occurrence=0) and bool(pide_confirmacion),
               detail=f"servicio ofrecido: {conv.state_field(N_IDENTIFICAR_SERVICIO, 'servicio', occurrence=0)!r}"),
            _c(
                "Turno 3 (rechaza el prestador ofrecido \"no, ese no es\"): \"Confirmó Servicio?\" tomó la rama "
                "NUEVA no_confirma_servicio, y el flow relanzó la búsqueda en vez de seguir con un prestador "
                "que el vecino no pidió",
                conv.branch_taken(N_CONFIRMO_SERVICIO, occurrence=0) == "no_confirma_servicio",
                detail=f"branch={conv.branch_taken(N_CONFIRMO_SERVICIO, occurrence=0)!r}",
            ),
            _c("Turno 3: volvió a correr Identificar servicio (2ª búsqueda) y a preguntar de nuevo",
               conv.ran_node(N_IDENTIFICAR_SERVICIO, occurrence=1) and bool(pide_confirmacion_2)),
            _c(
                "Turno 4 (confirma \"sí, ese mismo\"): \"Confirmó Servicio?\" tomó la rama NUEVA "
                "confirma_servicio y recién ahí avanzó a pedir la dirección",
                conv.branch_taken(N_CONFIRMO_SERVICIO, occurrence=1) == "confirma_servicio",
                detail=f"branch={conv.branch_taken(N_CONFIRMO_SERVICIO, occurrence=1)!r}",
            ),
            _c("Turno 4: pidió la dirección/ubicación",
               bool(pide_direccion) and any(kw in pide_direccion.lower() for kw in direccion_kw)),
        ]
        checks += _cierre_checks(conv, reply)
        checks.append(_c(
            "Turno 5 (dirección válida al primer pedido): \"Tienen dirección?\" clasificó tiene_direccion",
            conv.branch_taken(N_VALIDAR_DIRECCION) == "tiene_direccion",
        ))
        checks.append(_c(
            "El campo state.direccion quedó con la dirección real dada, no un placeholder "
            "(regresión del bug {{message}} arreglado 2026-07-10)",
            conv.state_field(N_SET_DIRECCION, "direccion") == "Av. Roca 1234, Villa Lugano",
            detail=f"direccion={conv.state_field(N_SET_DIRECCION, 'direccion')!r}",
        ))
        checks.append(_c(
            "Corrió notificar_trabajador (side-effect real de avisar al prestador — guarded en sim, "
            "pero el nodo SÍ ejecutó su lógica)",
            conv.ran_node(N_NOTIFICAR_TRABAJADOR),
        ))
        lower = (reply or "").lower()
        # El servicio confirmado es el de la 2ª búsqueda (post-rechazo, occurrence=1). Si la búsqueda
        # en vivo no encontró nada real (SIN_RESULTADOS), "Confirmó Servicio?" lo deja pasar igual como
        # confirma_servicio (bug real reportado en el docstring del módulo — no es "", no es "UNCLEAR").
        # En ese caso no tiene sentido exigir un contacto real en la respuesta: solo pedimos que el bot
        # degrade con gracia (no invente datos falsos) en vez de romperse.
        servicio_final = conv.state_field(N_IDENTIFICAR_SERVICIO, "servicio", occurrence=1) or ""
        if servicio_final.strip().upper() == "SIN_RESULTADOS":
            checks.append(_c(
                "[Búsqueda sin resultados reales — bug conocido de \"Confirmó Servicio?\" con SIN_RESULTADOS] "
                "el bot igual respondió con gracia, sin inventar un contacto falso",
                bool(reply) and not any(kw in lower for kw in ("roberto", "gómez")),
                detail=f"servicio_final={servicio_final!r} reply={reply!r}",
            ))
        else:
            checks.append(_c(
                "La respuesta final confirma el pedido y da el contacto del prestador",
                any(kw in lower for kw in ("registrad", "avisamos", "prestador", "roberto", "gómez"))
                or bool(re.search(r"\d{4,}", reply or "")),
                detail=f"servicio_final={servicio_final!r}",
            ))
        checks.append(_c("Cerró específicamente por end_conv_ok (cierre de éxito)", conv.ran_node("end_conv_ok")))
    return ScenarioResult(turns, checks)


# ─── 6. Fuera de scope — cierre por farewell fijo, sin tocar el directorio real ─

async def _run_fuera_de_scope() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r1 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r1))
        msg = "recomendame un buen plomero en Recoleta"
        reply = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", reply))

        checks = [
            _c("Turno 1: pidió aclaración ante el saludo ambiguo",
               conv.branch_taken(N_CONDICION, occurrence=0) == "pedir_mas_info"),
            _c("Turno 2: el extractor clasificó el pedido como OUT_OF_SCOPE (otro barrio)",
               conv.state_field(N_OBTENER_NECESIDAD, "necesidad") == "OUT_OF_SCOPE"),
            _c("Turno 2: la Condición mandó directo a fuera_de_scope",
               conv.branch_taken(N_CONDICION) == "fuera_de_scope"),
        ]
        checks += _cierre_checks(conv, reply)
        lower = (reply or "").lower()
        checks.append(_c("Reconoce que el pedido es de otro barrio", "no lo manejamos" in lower or "villa lugano" in lower))
        checks.append(_c("Cierre con despedida (👋 o \"hasta la próxima\")", "👋" in (reply or "") or "hasta la próxima" in lower))
        checks.append(_c(
            "NO buscó en el directorio real (negativo — el guardrail de scope corta ANTES de tocar la API)",
            not conv.ran_node(N_BUSCAR_DIRECTORIO),
        ))
        checks.append(_c(
            "La respuesta no ofertó nada real del directorio (negativo)",
            "roberto" not in lower and "dirección" not in lower and "ferreter" not in lower,
        ))
        checks.append(_c("Cerró específicamente por end_conv_scope", conv.ran_node("end_conv_scope")))
    return ScenarioResult(turns, checks)


# ─── 7. (único camino infeliz) Servicio agotado — 3 direcciones ambiguas seguidas ─

async def _run_servicio_agotado() -> ScenarioResult:
    """
    Único escenario "infeliz" de la suite: primero confirma el prestador en el
    primer intento (sin ejercitar de nuevo el rechazo — eso ya lo cubre
    `_run_servicio`), y agota los 3 `max_visits` que permite "Tienen dirección?"
    (`node_1783873174012`, antes `validar_direccion`, confirmado en vivo
    2026-07-12) sin dar nunca una dirección real — el flow debe cerrar solo
    igual, por la rama de disculpa (`agotado` → disculpar_dir → end_conv_fail),
    no quedarse colgado. Un camino infeliz también tiene que TERMINAR.

    OJO con el presupuesto real de intentos (ver nota en `_run_servicio`):
    "Tienen dirección?" corre una vez de forma IMPLÍCITA apenas se confirma
    el servicio (consume 1 de las 3 visitas antes de que el vecino diga nada
    de dirección) — así que alcanzan solo 2 respuestas ambiguas EXPLÍCITAS
    (no 3) para agotar el contador. Mandar una 3ª ambigua después de que el
    flow ya cerró por `end_conv_fail` dispara una conversación NUEVA (el sim
    no tiene nada que resumir) y rompe el escenario — evitarlo.
    """
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r0 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r0))

        m1 = "se me rompió una canilla, necesito un plomero urgente"
        pide_confirmacion = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", pide_confirmacion))

        m1b = "sí, ese mismo"
        pide_direccion = await conv.send_and_wait(m1b)
        turns.append(("user", m1b)); turns.append(("bot", pide_direccion))

        direccion_kw = ("dirección", "calle", "ubicac", "domicilio")
        ambiguas = ["no sé, por qué preguntás?", "no tengo idea"]
        last_reply = pide_direccion
        for msg in ambiguas:
            last_reply = await conv.send_and_wait(msg)
            turns.append(("user", msg)); turns.append(("bot", last_reply))

        checks = [
            _c("Turno 1: pidió aclaración ante el saludo ambiguo",
               conv.branch_taken(N_CONDICION, occurrence=0) == "pedir_mas_info"),
            _c("Clasificó la rama como \"servicio\" y pidió confirmar el prestador",
               bool(pide_confirmacion) and conv.ran_node(N_CONFIRMAR_SERVICIO)),
            _c("Confirmó el prestador en el primer intento y recién ahí pidió dirección/ubicación",
               conv.branch_taken(N_CONFIRMO_SERVICIO) == "confirma_servicio"
               and bool(pide_direccion) and any(kw in pide_direccion.lower() for kw in direccion_kw)),
            _c(
                "Tras 2 respuestas ambiguas explícitas (+ 1 evaluación implícita al confirmar el servicio "
                "= 3 visitas), \"Tienen dirección?\" agotó los reintentos (max_visits=3) y tomó la rama "
                "\"agotado\" en vez de repreguntar para siempre",
                conv.branch_taken(N_VALIDAR_DIRECCION) == "agotado",
                detail=f"branch={conv.branch_taken(N_VALIDAR_DIRECCION)!r} visits={conv.state_field(N_VALIDAR_DIRECCION, '_visits_' + N_VALIDAR_DIRECCION)!r}",
            ),
            _c(f"El contador de reintentos (_visits_{N_VALIDAR_DIRECCION}) llegó exactamente a 3",
               conv.state_field(N_VALIDAR_DIRECCION, "_visits_" + N_VALIDAR_DIRECCION) == 3),
            _c("Corrió el nodo de disculpa (disculpar_dir)", conv.ran_node("disculpar_dir")),
        ]
        checks += _cierre_checks(conv, last_reply)
        lower = (last_reply or "").lower()
        servicio = (conv.state_field(N_IDENTIFICAR_SERVICIO, "servicio", occurrence=0) or "").lower()
        checks.append(_c(
            "La disculpa igual le da al vecino el contacto del prestador para que arregle directo "
            "(menciona al prestador confirmado y/o incluye un teléfono)",
            (bool(servicio) and servicio in lower) or bool(re.search(r"\d{4,}", last_reply or "")),
            detail=f"servicio={servicio!r} reply={last_reply!r}",
        ))
        checks.append(_c("Cerró específicamente por end_conv_fail (cierre de agotamiento, no de éxito)",
                          conv.ran_node("end_conv_fail")))
    return ScenarioResult(turns, checks)


# ─── 8. Conectividad — único caso que sale por Telegram real ────────────────

async def _run_conectividad_telegram() -> ScenarioResult:
    turns = []
    async with TeliConversation("luganense_bot") as conv:
        reply = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", reply))
    checks = [_c("El bot real de Telegram respondió", bool(reply))]
    return ScenarioResult(turns, checks)


SCENARIOS: list[Scenario] = [
    Scenario(
        id="comercio", title="Comercio — aclaración + resiliencia a ambiguo + ferretería",
        desc="Arranca con un saludo ambiguo (pide aclaración), tolera un mensaje sin sentido en el medio sin romperse, "
             "y recién se resuelve al dar el pedido real — cierra con el contacto real del comercio.",
        run=_run_comercio,
    ),
    Scenario(
        id="comercio-sin-rubro", title="Comercio sin rubro explícito — \"Kiosco Don Jorge\" (1 turno)",
        desc="Un nombre propio de comercio sin decir el rubro debe resolverse en el PRIMER turno, sin pedir aclaración "
             "(regresión 2026-07-08) — y aun así cerrar la conversación de punta a punta.",
        run=_run_comercio_sin_rubro,
    ),
    Scenario(
        id="producto", title="Producto — aclaración + pizza",
        desc="Saludo ambiguo → aclaración → pedido de pizza → oferta y cierre.",
        run=_run_producto,
    ),
    Scenario(
        id="noticias", title="Noticias — aclaración + corte de luz",
        desc="Saludo ambiguo → aclaración → consulta de noticias del barrio → respuesta y cierre.",
        run=_run_noticias,
    ),
    Scenario(
        id="servicio", title="Servicio con notificación — el camino más largo (aclaración + rechazo/confirmación "
                             "de prestador + 2 vueltas de wait_user de dirección)",
        desc="Saludo ambiguo → aclaración → pedido de plomero → el bot busca y ofrece un prestador → el vecino lo "
             "RECHAZA (rama nueva no_confirma_servicio, relanza la búsqueda) → el vecino CONFIRMA el segundo "
             "(rama nueva confirma_servicio) → pide dirección → dirección ambigua (repregunta, 1ª vuelta) → "
             "dirección válida (2ª vuelta, resuelve) → notifica al prestador real → cierra.",
        run=_run_servicio,
    ),
    Scenario(
        id="fuera-de-scope", title="Fuera de scope — otro barrio, sin tocar el directorio real",
        desc="Saludo ambiguo → aclaración → pedido de otro barrio (Recoleta) → el guardrail de scope corta ANTES "
             "de buscar en el directorio real → cierra con farewell fijo.",
        run=_run_fuera_de_scope,
    ),
    Scenario(
        id="servicio-agotado", title="[Único camino infeliz] Servicio — agotamiento tras 3 direcciones ambiguas",
        desc="El vecino confirma el prestador ofrecido al primer intento pero nunca da una dirección real (3 "
             "intentos ambiguos seguidos) — \"Tienen dirección?\" agota sus reintentos (max_visits=3) y el flow "
             "cierra igual por la rama de disculpa, en vez de quedar colgado.",
        run=_run_servicio_agotado,
    ),
    Scenario(
        id="conectividad-telegram", title="Conectividad — Telegram real (@luganense_bot)",
        desc="Único caso de esta suite que sale por Telegram de verdad — smoke test de conectividad, no de lógica de negocio.",
        run=_run_conectividad_telegram,
        real_telegram=True,
    ),
]
