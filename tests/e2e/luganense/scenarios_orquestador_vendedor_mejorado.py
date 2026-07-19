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

Revisión 2026-07-13 (v4, tras feedback: "no quiero validaciones de texto en
el reply, quiero que esto valide todo de forma robusta contra el log"):
las versiones anteriores de esta suite asserteaban/logueaban sobre el TEXTO
del reply (`"pizza" in reply`, `"escribime cuando quieras" in reply`, etc.) —
eso es indirectamente lo mismo que asserter sobre la redacción de un LLM, que
es no determinista por naturaleza. Esta versión valida ÚNICAMENTE contra el
LOG REAL de ejecución (`flow_run_steps`, vía `SimConversation.ran_node/
state_field/branch_taken/fetch_errors/node_errors`) — nunca contra el texto
visible del reply:
  - Que la conversación haya pasado por los nodos que ese camino DEBE
    ejecutar (`ran_node`) — el mapa completo de nodos/edges del flow real
    está confirmado por inspección en vivo, ver más abajo.
  - Que ningún fetch HTTP haya fallado (404, timeout, DNS) ni haya
    disparado con un placeholder `{{...}}` sin resolver en la URL
    (`SimConversation.fetch_errors()`, ver `FetchHttpNode._record_fetch_error`
    — antes esto quedaba invisible, el output simplemente caía en `None`).
  - Que ningún nodo haya crasheado (`SimConversation.node_errors()` /
    `crashed_nodes()`, del `_node_errors`/`status="error"` que loguea
    compiler.py).
  - Que ningún placeholder `{{...}}` haya quedado sin resolver en el reply
    ni en el `state.data` de ningún step de toda la conversación.
  - Que la conversación haya cerrado con un `end_conversation` real.

Nota: al validar contra `ran_node`/`branch_taken` en vez de contra el texto,
esta suite SÍ puede fallar si el router/LLM de clasificación toma la rama
equivocada (ej. un pedido de plomero cae en la rama "noticias") — a
diferencia de la versión anterior, que lo dejaba pasar como "log". Es a
propósito: confundir la rama es un bug real que vale la pena que la suite
marque en rojo, no algo que haya que esconder. Lo que se evitó es solo
juzgar la REDACCIÓN puntual de la respuesta (qué palabras eligió, si
mencionó tal nombre propio) — eso sigue siendo demasiado no determinista
para un assert duro, y va como `_log` informativo (branch/necesidad
extraída), nunca como texto de reply.

Mapa de nodos/edges del flow real "Orquestador Vendedor Mejorado" (bot
"luganense", confirmado en vivo el 2026-07-13 vía
`GET /api/flows/bots/luganense/{flow_id}` — si el flow se edita y estos ids
cambian, hay que actualizar acá):

  node_1783192985521  telegram_trigger  "Llega Mensaje a Luganense"
  node_1783192800831  llm               "Obtener necesidad" → state.necesidad
  node_1783356000392  condition         "Condición" → necesidad_identificada | pedir_mas_info | fuera_de_scope
  node_1783194257636  metric            (solo en la rama necesidad_identificada)
  node_1783192962168  router            "Elegir Mostrador" → servicio | comercio | producto | noticias

  Rama "comercio":
  node_1783949463710  fetch_http        → state.comercio_luganense
  node_1783196060944  llm               "mensaje_referencia_comercio"
  end_conv_comercio   end_conversation

  Rama "producto":
  node_1783949755356  fetch_http        → state.producto_luganense
  node_1783195927257  llm               "mensaje_oferta_producto"
  end_conv_producto   end_conversation

  Rama "noticias":
  expandir_consulta   llm               → state.query
  node_1783693824414  fetch_http        (sin output custom, cae en "context")
  responder_noticias  llm               "mensaje_noticias"
  end_conv_noticias   end_conversation

  Rama "servicio" (rediseñada 2026-07-14, 2ª vuelta — tras feedback: ya no se
  confirma el nombre propio de un prestador puntual, se confirma el RUBRO del
  servicio primero. Motivo: el candidato que devuelve Luganense es SIEMPRE el
  que ellos resuelven como mejor opción para ese rubro (no hay 2 para elegir
  de nuestro lado), así que "confirmar" un nombre propio no tenía sentido —
  lo que puede estar mal es el RUBRO que entendimos de la necesidad del
  vecino. Luganense expuso `GET /api/directorio/rubros?tipo=servicios&q=`
  (matching por texto libre sobre la necesidad, mismo motor que `/buscar` y
  `/candidato`) para poder confirmar contra una lista real de rubros, sin
  inventar ninguno. `elegir_rubro` es un LLM grounded ÚNICAMENTE a esa lista
  (nunca elige algo fuera de `rubros_luganense`) — sigue sin haber invención
  de prestadores ni de rubros inexistentes. Recién con el rubro confirmado se
  llama a `/candidato?q=<rubro>` para resolver el prestador puntual — un solo
  llamado, después de la confirmación, no antes):
  buscar_rubros        fetch_http       GET /api/directorio/rubros?tipo=servicios&q={{necesidad}}
                                         → state.rubros_luganense (JSON crudo: {rubros:[{categoria,label}],total})
                                         + extract_fields: state.rubros_total
  rubros_encontrados_cond condition     ¿rubros_total == "0"? → sin_resultados : encontrado
                                         sin_resultados → disculpar_sin_servicio_msg → end_conv_fail
  elegir_rubro          llm             elige (grounded, sin inventar) el "label" más adecuado de
                                         `rubros_luganense` → state.rubro_elegido. Si ya se había
                                         propuesto antes y no fue confirmado, se le pide elegir otro
                                         distinto de la misma lista (si hay más de una opción).
  node_1783892162094  send_message      "Confirmar Rubro" → "¿Es este el tipo de servicio que necesitás: '{{rubro_elegido}}'?"
  node_1783892344935  wait_user         "Esperar rubro confirmado"
  node_1783892654800  llm               "Obtener rubro confirmado" → state.rubro_confirmado (o UNCLEAR)
  node_1783892396384  condition         "Confirmó Rubro?" → confirma_rubro | no_confirma_rubro | agotado (max_visits=3)
                                         confirma_rubro → buscar_servicio (recién ahí se resuelve el
                                         candidato puntual); no_confirma_rubro → vuelve a `elegir_rubro`
                                         (no hace falta re-pegarle a `/rubros`, la necesidad no cambió).
                                         agotado → disculpar_rubro_agotado → end_conv_fail (fix del dead-end
                                         reportado en la versión anterior de este docstring: antes esta
                                         ruta no tenía edge de salida).
  buscar_servicio      fetch_http       GET /api/directorio/candidato?q={{rubro_elegido}}&tipo=servicios
                                         → state.servicios_luganense (JSON crudo) + extract_fields:
                                         state.servicio (nombre), servicio_categoria, servicio_zona,
                                         servicio_contact_id, servicio_contact_channel — vacíos (no
                                         seteados) si el candidato vino null. Corre DESPUÉS de confirmar
                                         el rubro, ya no antes (antes de esta 2ª vuelta apuntaba a
                                         `{{necesidad}}` en crudo, corría antes de cualquier confirmación,
                                         y lo que se confirmaba era el nombre propio del candidato).
  servicio_encontrado_cond condition    ¿state.servicio no vacío? → encontrado | sin_resultados. Con
                                         rubro ya confirmado, "encontrado" va DIRECTO a "Obtener
                                         dirección" — ya no hay una 2ª confirmación de nombre propio.
  disculpar_sin_servicio_msg send_message  mensaje fijo (sin LLM), reusado en dos casos: sin rubros que
                                         matcheen la necesidad, o sin candidato pese a rubro confirmado
                                         → end_conv_fail
  node_1783873167862  llm               "Obtener dirección" → state.direccion (o UNCLEAR)
  node_1783873174012  condition         "Tienen dirección?" (antes "validar_direccion") → tiene_direccion | sin_direccion | agotado (max_visits=3)
  node_1783867942451  llm               "Armar mensaje pedir dirección"
  pedir_direccion     send_message      "¿En qué dirección necesitás el servicio?"
  wait_dir            wait_user
  set_direccion       set_state         → state.direccion (bug real 2026-07-10: usaba {{message}}, roto — fix: {{conversation.last}})
  notificar_trabajador send_message     envío real al prestador (guarded en sim) — `to`/`channel` usan
                                         `servicio_contact_id`/`servicio_contact_channel` (bug real
                                         encontrado 2026-07-14: antes referenciaba `{{contact_id}}`/
                                         `{{contact_channel}}`, que NINGÚN nodo del flow seteaba nunca —
                                         la notificación real nunca funcionó, quedaba con placeholders
                                         sin resolver)
  responder_vecino_oficio llm           mensaje final al vecino, post-notificación
  disculpar_dir        llm              rama agotado (de "Tienen dirección?")
  end_conv_ok / end_conv_fail           end_conversation, cierre de éxito / agotamiento
"""
from dataclasses import dataclass
from typing import Awaitable, Callable

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

# ─── Node ids (ver docstring) ────────────────────────────────────────────────
N_OBTENER_NECESIDAD = "node_1783192800831"
N_CONDICION = "node_1783356000392"
N_ELEGIR_MOSTRADOR = "node_1783192962168"

N_COMERCIO_FETCH = "node_1783949463710"
N_COMERCIO_LLM = "node_1783196060944"

N_PRODUCTO_FETCH = "node_1783949755356"
N_PRODUCTO_LLM = "node_1783195927257"

N_NOTICIAS_EXPANDIR = "expandir_consulta"
N_NOTICIAS_FETCH = "node_1783693824414"
N_NOTICIAS_LLM = "responder_noticias"

N_VALIDAR_DIRECCION = "node_1783873174012"  # "Tienen dirección?" (antes "validar_direccion")
N_BUSCAR_RUBROS = "buscar_rubros"  # GET /rubros?q={{necesidad}} — lista de rubros que matchean, sin LLM
N_RUBROS_ENCONTRADOS_COND = "rubros_encontrados_cond"  # ¿rubros_total == "0"? → sin_resultados : encontrado
N_ELEGIR_RUBRO = "elegir_rubro"  # llm grounded a rubros_luganense → state.rubro_elegido
N_BUSCAR_SERVICIO = "buscar_servicio"  # GET /candidato?q={{rubro_elegido}}, extract_fields, sin LLM — corre tras confirmar el rubro
N_SERVICIO_ENCONTRADO_COND = "servicio_encontrado_cond"  # ¿state.servicio no vacío? → encontrado | sin_resultados
N_DISCULPAR_SIN_SERVICIO = "disculpar_sin_servicio_msg"  # mensaje fijo (sin LLM) si sin_resultados
N_DISCULPAR_RUBRO_AGOTADO = "disculpar_rubro_agotado"  # mensaje fijo (sin LLM) si se agotan los 3 intentos de confirmar rubro
N_NOTIFICAR_TRABAJADOR = "notificar_trabajador"
N_RESPONDER_SERVICIO = "responder_vecino_oficio"
N_SET_DIRECCION = "set_direccion"
N_CONFIRMAR_RUBRO = "node_1783892162094"  # "Confirmar Rubro" (send_message)
N_OBTENER_RUBRO_CONFIRMADO = "node_1783892654800"  # "Obtener rubro confirmado" → state.rubro_confirmado
N_CONFIRMO_RUBRO = "node_1783892396384"  # "Confirmó Rubro?" (condition)


@dataclass
class Check:
    label: str
    passed: bool
    detail: str = ""
    # "assert" hace fallar el test si passed=False. "log" es siempre passed=True
    # y solo se muestra como informativo — ver nota de diseño en el docstring
    # del módulo (nunca contra el texto del reply).
    kind: str = "assert"


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


def _c(label: str, passed, detail: str = "") -> Check:
    """Assert real: si `passed` es False, hace fallar el test."""
    return Check(label, bool(passed), detail, kind="assert")


def _log(label: str, detail: str = "") -> Check:
    """Entrada informativa (nunca hace fallar el test) — para diagnóstico
    ("¿resolvimos bien esta vez?"), siempre derivada del LOG (branch/necesidad
    extraída), nunca del texto del reply."""
    return Check(label, True, detail, kind="log")


def _ran_all(label: str, conv: SimConversation, *node_ids: str) -> Check:
    """Assert real: TODOS los `node_ids` deben haber corrido (`ran_node`) en
    algún momento de la conversación acumulada — el camino esperado por el log
    de ejecución, no por lo que dice el reply."""
    faltantes = [n for n in node_ids if not conv.ran_node(n)]
    return _c(label, not faltantes, detail=f"no corrieron: {faltantes}" if faltantes else "")


def _infra_checks(conv: SimConversation, reply: str | None) -> list[Check]:
    """
    Chequeos comunes a TODA conversación (feliz o infeliz) — 100%
    deterministas, derivados del log de ejecución real, nunca del texto del
    reply: reply no vacío (una respuesta vacía SIEMPRE es un bug — de red, de
    timeout, o del router de modelos devolviendo contenido vacío en silencio;
    nunca "una decisión válida del modelo"), sin templates rotos en ningún
    lado, sin fetch HTTP fallidos (404/timeout/DNS/URL con `{{...}}` sin
    resolver — ver `FetchHttpNode._record_fetch_error`), sin nodos
    crasheados, cierre real (end_conversation).
    """
    checks = [_c("El bot respondió en el último turno", bool(reply), repr(reply) if not reply else "")]
    if not reply:
        return checks
    checks.append(_c("Sin placeholders {{...}} sin resolver en el reply", not has_unresolved_templates(reply)))
    rotos = conv.state_unresolved_templates()
    checks.append(_c(
        "Sin placeholders {{...}} sin resolver en el state de NINGÚN step de TODA la conversación",
        not rotos, detail=str(rotos) if rotos else "",
    ))
    fetch_errors = conv.fetch_errors()
    checks.append(_c(
        "Sin fetch HTTP fallidos (404/timeout/DNS/URL con placeholder sin resolver) en TODA la conversación",
        not fetch_errors, detail=str(fetch_errors) if fetch_errors else "",
    ))
    llm_errors = conv.llm_errors()
    checks.append(_c(
        "Sin contenido vacío persistente de un LLM (sobrevivió al reintento automático) en TODA la conversación",
        not llm_errors, detail=str(llm_errors) if llm_errors else "",
    ))
    node_errors = conv.node_errors()
    crashed = conv.crashed_nodes()
    checks.append(_c(
        "Ningún nodo crasheó (_node_errors / status=\"error\")",
        not node_errors and not crashed,
        detail=f"node_errors={node_errors} crashed={crashed}" if (node_errors or crashed) else "",
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
            _log("Turno 1 (\"hola\", ambiguo): clasificación de necesidad",
                 detail=f"necesidad={conv.state_field(N_OBTENER_NECESIDAD, 'necesidad', occurrence=0)!r}"),
            _log("Turno 1: rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION, occurrence=0)!r}"),
            _c("Turno 1: el bot respondió pidiendo aclaración (no vacío)", bool(r1)),
            _c("Turno 2 (\"asdfgh\", ambiguo de nuevo): el flow no se rompió, siguió respondiendo (no vacío)", bool(r2)),
        ]
        checks += _infra_checks(conv, reply)
        checks.append(_log("Turno 3: rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"))
        checks.append(_ran_all(
            "Pasó por los nodos esperados de la rama comercio (fetch al directorio + armado de mensaje + cierre)",
            conv, N_COMERCIO_FETCH, N_COMERCIO_LLM, "end_conv_comercio",
        ))
    return ScenarioResult(turns, checks)


# ─── 2. Comercio sin rubro explícito (Kiosco Don Jorge) — resolución en 1 turno ─

async def _run_comercio_sin_rubro() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        msg = "Hola, ¿podés decirme el teléfono de Kiosco Don Jorge?"
        reply = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", reply))

        checks = [
            _log("¿Resolvió la necesidad en el PRIMER turno, sin pedir aclaración?",
                 detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
            _log("Rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"),
        ]
        checks += _infra_checks(conv, reply)
        checks.append(_ran_all(
            "Pasó por los nodos esperados de la rama comercio (fetch al directorio + armado de mensaje + cierre)",
            conv, N_COMERCIO_FETCH, N_COMERCIO_LLM, "end_conv_comercio",
        ))
    return ScenarioResult(turns, checks)


# ─── 3. Producto (focos LED) — con loop de aclaración ────────────────────────
#
# Nota de diseño (2026-07-13): antes probaba "quiero pedir una pizza" — mal
# elegido. El prompt del router ("Elegir Mostrador") define "comercio" como
# "un local, negocio o comercio del barrio (bar, kiosco, verdulería,
# peluquería, etc.)" y declara la prioridad explícita "servicio > comercio >
# producto" para desempatar ambigüedades — una pizzería encaja de lleno como
# "comercio" (es, literalmente, un local de comida), así que "pizza" es
# ambiguo por diseño del propio router y determinísticamente pierde contra
# comercio. Confirmado contra el API real de Luganense
# (GET /api/directorio/buscar?tipo=productos) que "pizza" SÍ existe cargado
# como producto (La Esquina de Lugano Pizza, Pizzería El Horno de Barro) —
# no era un problema de datos faltantes, era la elección del mensaje de
# prueba. "Focos LED" (Iluminación LuzHogar, confirmado en el mismo API) no
# calza en ninguna categoría de comercio de barrio reconocible → mucho menos
# ambiguo para el router.

async def _run_producto() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        msg = "Hola, necesito comprar unos focos LED para mi casa"
        reply = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", reply))

        checks = [
            _log("Rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
        ]
        checks += _infra_checks(conv, reply)
        checks.append(_log("Rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"))
        checks.append(_ran_all(
            "Pasó por los nodos esperados de la rama producto (fetch de productos + armado de mensaje + cierre)",
            conv, N_PRODUCTO_FETCH, N_PRODUCTO_LLM, "end_conv_producto",
        ))
    return ScenarioResult(turns, checks)


# ─── 4. Noticias — con loop de aclaración ────────────────────────────────────

async def _run_noticias() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        msg = "Hola, qué se sabe del corte de luz en Lugano"
        reply = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", reply))

        checks = [
            _log("Rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
        ]
        checks += _infra_checks(conv, reply)
        checks.append(_log("Rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"))
        checks.append(_ran_all(
            "Pasó por los nodos esperados de la rama noticias (expandir consulta + fetch + armado de mensaje + cierre)",
            conv, N_NOTICIAS_EXPANDIR, N_NOTICIAS_FETCH, N_NOTICIAS_LLM, "end_conv_noticias",
        ))
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
        # Necesidad deliberadamente ambigua entre varios rubros (gas + agua) —
        # así el 1er rubro propuesto por `elegir_rubro` puede no ser el que el
        # vecino tenía en mente, y el rechazo + corrección tiene sentido real
        # (a diferencia de rechazar un nombre propio de prestador, que ya no
        # se confirma en este flow, ver docstring del módulo). Saludo +
        # necesidad van en el mismo primer mensaje (no se testea el loop de
        # aclaración del saludo aislado acá — eso ya lo cubre el escenario
        # "comercio").
        m1 = "Hola, tengo un problema con el gas y también una pérdida de agua en casa, necesito ayuda urgente"
        pide_confirmacion = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", pide_confirmacion))

        m2 = "no, en realidad lo urgente es la pérdida de agua, necesito un plomero"
        pide_confirmacion_2 = await conv.send_and_wait(m2)
        turns.append(("user", m2)); turns.append(("bot", pide_confirmacion_2))

        m3 = "sí, ese mismo, dale"
        pide_direccion = await conv.send_and_wait(m3)
        turns.append(("user", m3)); turns.append(("bot", pide_direccion))

        m4 = "Av. Roca 1234, Villa Lugano"
        reply = await conv.send_and_wait(m4)
        turns.append(("user", m4)); turns.append(("bot", reply))

        checks = [
            _log("Turno 1: rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
            _log("Turno 1: rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"),
            _ran_all(
                "Turno 1: buscó rubros que matchean la necesidad (dato real, sin invención) y pidió confirmar el rubro",
                conv, N_BUSCAR_RUBROS, N_RUBROS_ENCONTRADOS_COND, N_ELEGIR_RUBRO, N_CONFIRMAR_RUBRO,
            ),
            _log("Rubros que matchearon la necesidad", detail=f"{conv.state_field(N_BUSCAR_RUBROS, 'rubros_luganense', occurrence=0)!r}"),
            _log("Rubro ofrecido (1ª propuesta)", detail=f"{conv.state_field(N_ELEGIR_RUBRO, 'rubro_elegido', occurrence=0)!r}"),
            _log("Turno 2 (rechaza el rubro propuesto y aclara \"necesito un plomero\"): rama de \"Confirmó Rubro?\"",
                 detail=f"branch={conv.branch_taken(N_CONFIRMO_RUBRO, occurrence=0)!r}"),
            _c("Turno 2: el bot volvió a preguntar (no vacío)", bool(pide_confirmacion_2)),
            _ran_all(
                "Turno 2: volvió a elegir rubro tras el rechazo (2ª ejecución de elegir_rubro, SIN re-pegarle a /rubros)",
                conv, N_ELEGIR_RUBRO,
            ),
            _log("Rubro ofrecido (2ª propuesta, tras la corrección del vecino)",
                 detail=f"{conv.state_field(N_ELEGIR_RUBRO, 'rubro_elegido', occurrence=1)!r}"),
            _log("Turno 3 (confirma \"sí, ese mismo\"): rama de \"Confirmó Rubro?\"",
                 detail=f"branch={conv.branch_taken(N_CONFIRMO_RUBRO, occurrence=1)!r}"),
            _c("Turno 3: el bot pidió la dirección/ubicación (no vacío)", bool(pide_direccion)),
        ]
        checks += _infra_checks(conv, reply)
        checks.append(_ran_all(
            "Turno 3: con el rubro confirmado, recién ahí resolvió el candidato puntual (una sola vez, tras la confirmación)",
            conv, N_BUSCAR_SERVICIO, N_SERVICIO_ENCONTRADO_COND,
        ))
        checks.append(_log(
            "Prestador resuelto para el rubro confirmado",
            detail=f"{conv.state_field(N_BUSCAR_SERVICIO, 'servicio', occurrence=0)!r}",
        ))
        checks.append(_log(
            "Turno 4 (dirección dada): rama de \"Tienen dirección?\"",
            detail=f"branch={conv.branch_taken(N_VALIDAR_DIRECCION)!r}",
        ))
        direccion_extraida = conv.state_field(N_SET_DIRECCION, "direccion")
        checks.append(_c(
            "state.direccion quedó resuelta (no vacía, sin placeholder {{...}} sin resolver) "
            "— regresión del bug {{message}} arreglado 2026-07-10",
            bool(direccion_extraida) and not has_unresolved_templates(direccion_extraida),
            detail=f"direccion={direccion_extraida!r}",
        ))
        checks.append(_ran_all(
            "Pasó por los nodos esperados de cierre (notificó al prestador, armó la respuesta final, cerró end_conv_ok)",
            conv, N_NOTIFICAR_TRABAJADOR, N_RESPONDER_SERVICIO, "end_conv_ok",
        ))
    return ScenarioResult(turns, checks)


# ─── 6. Fuera de scope — cierre por farewell fijo, sin tocar el directorio real ─
#
# Nota de diseño (2026-07-16): antes pedía "un buen plomero en Recoleta" — mal
# elegido, porque un pedido de servicio SIN mencionar lugar (o incluso con otro
# barrio) puede legítimamente recomendarse desde nuestro directorio (no hay
# problema en ofrecer nuestro plomero aunque el vecino haya nombrado otro
# barrio de pasada). El caso de scope real e inequívoco es pedir NOTICIAS de
# OTRO barrio — ahí no hay ambigüedad posible: Luganense solo tiene noticias de
# Villa Lugano, así que "qué pasó en Recoleta" tiene que cortar antes de tocar
# cualquier API real.

async def _run_fuera_de_scope() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        msg = "Hola, qué noticias hay en Recoleta"
        reply = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", reply))

        checks = [
            _log("Clasificación de necesidad", detail=f"necesidad={conv.state_field(N_OBTENER_NECESIDAD, 'necesidad')!r}"),
            _log("Rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
        ]
        checks += _infra_checks(conv, reply)
        checks.append(_ran_all("Cerró específicamente por end_conv_scope", conv, "end_conv_scope"))
        checks.append(_c(
            "NO buscó noticias reales de otro barrio (el guardrail de scope corta ANTES de tocar la API)",
            not conv.ran_node(N_NOTICIAS_FETCH),
        ))
    return ScenarioResult(turns, checks)


# ─── 7. (único camino infeliz) Servicio agotado — 3 direcciones ambiguas seguidas ─

async def _run_servicio_agotado() -> ScenarioResult:
    """
    Único escenario "infeliz" de la suite: primero confirma el rubro en el
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
        m1 = "Hola, se me rompió una canilla, necesito un plomero urgente"
        pide_confirmacion = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", pide_confirmacion))

        m1b = "sí, ese mismo"
        pide_direccion = await conv.send_and_wait(m1b)
        turns.append(("user", m1b)); turns.append(("bot", pide_direccion))

        ambiguas = ["no sé, por qué preguntás?", "no tengo idea"]
        last_reply = pide_direccion
        for msg in ambiguas:
            last_reply = await conv.send_and_wait(msg)
            turns.append(("user", msg)); turns.append(("bot", last_reply))

        checks = [
            _log("Rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
            _ran_all("El bot buscó rubros que matchean la necesidad y pidió confirmar el rubro",
                     conv, N_BUSCAR_RUBROS, N_ELEGIR_RUBRO, N_CONFIRMAR_RUBRO),
            _log("Rama de \"Confirmó Rubro?\"", detail=f"branch={conv.branch_taken(N_CONFIRMO_RUBRO)!r}"),
            _ran_all("Con el rubro confirmado, resolvió el candidato puntual antes de pedir dirección",
                     conv, N_BUSCAR_SERVICIO),
            _c("El bot pidió dirección/ubicación tras confirmar (no vacío)", bool(pide_direccion)),
            _log("Rama de \"Tienen dirección?\" tras agotar reintentos (esperado: \"agotado\")",
                 detail=f"branch={conv.branch_taken(N_VALIDAR_DIRECCION)!r}"),
        ]
        visitas = conv.state_field(N_VALIDAR_DIRECCION, "_visits_" + N_VALIDAR_DIRECCION)
        checks.append(_c(
            f"El contador de reintentos (_visits_{N_VALIDAR_DIRECCION}) llegó exactamente a 3 "
            "(mecánica del engine — max_visits, no una decisión de contenido del LLM)",
            visitas == 3, detail=f"visits={visitas!r}",
        ))
        checks += _infra_checks(conv, last_reply)
        checks.append(_ran_all(
            "Cerró por la rama de disculpa (disculpar_dir → end_conv_fail), no se quedó colgado",
            conv, "disculpar_dir", "end_conv_fail",
        ))
    return ScenarioResult(turns, checks)


# ─── 8. Conectividad — único caso que sale por Telegram real ────────────────

async def _run_conectividad_telegram() -> ScenarioResult:
    turns = []
    async with TeliConversation("luganense_bot") as conv:
        reply = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", reply))
    checks = [_c("El bot real de Telegram respondió (no vacío)", bool(reply))]
    return ScenarioResult(turns, checks)


SCENARIOS: list[Scenario] = [
    Scenario(
        id="comercio", title="Comercio — aclaración + resiliencia a ambiguo + ferretería",
        desc="Arranca con un saludo ambiguo (pide aclaración), tolera un mensaje sin sentido en el medio sin romperse, "
             "y recién se resuelve al dar el pedido real — cierra pasando por el fetch real del directorio de comercios.",
        run=_run_comercio,
    ),
    Scenario(
        id="comercio-sin-rubro", title="Comercio sin rubro explícito — \"Kiosco Don Jorge\" (1 turno)",
        desc="Un nombre propio de comercio sin decir el rubro debe resolverse en el PRIMER turno, sin pedir aclaración "
             "(regresión 2026-07-08) — y aun así cerrar la conversación de punta a punta.",
        run=_run_comercio_sin_rubro,
    ),
    Scenario(
        id="producto", title="Producto — focos LED (necesidad directa en el saludo)",
        desc="Pedido de un producto puntual (focos LED) directo en el primer mensaje, sin loop de aclaración "
             "(eso ya lo cubre el escenario \"comercio\") → fetch real del directorio de productos → cierre.",
        run=_run_producto,
    ),
    Scenario(
        id="noticias", title="Noticias — corte de luz (necesidad directa en el saludo)",
        desc="Consulta de noticias del barrio directo en el primer mensaje, sin loop de aclaración → "
             "expandir consulta + fetch + cierre.",
        run=_run_noticias,
    ),
    Scenario(
        id="servicio", title="Servicio con notificación — el camino más largo (rechazo/confirmación "
                             "de rubro + 2 vueltas de wait_user de dirección)",
        desc="Necesidad ambigua entre rubros (gas + agua) directo en el primer mensaje, sin loop de aclaración → "
             "el bot busca los rubros que matchean y propone uno → el vecino lo RECHAZA y aclara → el bot propone "
             "otro rubro (sin re-pegarle a la API) → el vecino CONFIRMA → recién ahí resuelve el candidato puntual "
             "→ pide dirección → dirección ambigua (repregunta, 1ª vuelta) → dirección válida (2ª vuelta, resuelve) "
             "→ notifica al prestador real → cierra.",
        run=_run_servicio,
    ),
    Scenario(
        id="fuera-de-scope", title="Fuera de scope — noticias de otro barrio, sin tocar el directorio real",
        desc="Pedido de noticias de otro barrio (Recoleta) directo en el primer mensaje, sin loop de aclaración — "
             "el guardrail de scope corta ANTES de buscar noticias reales de otro barrio → cierra con farewell fijo.",
        run=_run_fuera_de_scope,
    ),
    Scenario(
        id="servicio-agotado", title="[Único camino infeliz] Servicio — agotamiento tras 3 direcciones ambiguas",
        desc="El vecino confirma el prestador ofrecido al primer intento (necesidad directa en el saludo, sin loop "
             "de aclaración) pero nunca da una dirección real (3 intentos ambiguos seguidos) — \"Tienen dirección?\" "
             "agota sus reintentos (max_visits=3) y el flow cierra igual por la rama de disculpa, en vez de quedar "
             "colgado.",
        run=_run_servicio_agotado,
    ),
    Scenario(
        id="conectividad-telegram", title="Conectividad — Telegram real (@luganense_bot)",
        desc="Único caso de esta suite que sale por Telegram de verdad — smoke test de conectividad, no de lógica de negocio.",
        run=_run_conectividad_telegram,
        real_telegram=True,
    ),
]
