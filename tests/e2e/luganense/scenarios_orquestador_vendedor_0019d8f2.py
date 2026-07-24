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

  "Obtener Necesidad" (nodo_flow → sub-flow reusable "get_data", 2026-07-19/20
  — patrón A: primero revisa si el dato ya está en la conversación, si no,
  pregunta; ver docstring del propio get_data). Expandido en runtime con
  prefijo `node_1784503628687::`:
  node_1784503628687::node_1783192800831  llm        "Identificar dato" → state.necesidad
  node_1784503628687::node_1783356000392  condition  "Condición dato identificado" → found | pedir_mas_info | not_found

  node_1783194257636  metric            (solo en la rama found)
  node_1783192962168  router            "Elegir Mostrador" → servicio | comercio | producto | noticias

  Rama "comercio" (migrada 2026-07-21 al mismo patrón B ("confirm_choice") que
  "noticias"/"servicio" — antes armaba un mensaje libre con TODOS los
  resultados crudos en un solo turno, sin confirmar nada; ahora propone UN
  comercio del directorio y pregunta si es ese, igual que noticias):
  node_1783949463710  fetch_http        "Buscar comercio" → state.comercio_luganense
                                        (JSON crudo {results:[{nombre,rubro,
                                        descripcion,direccion,contactos,
                                        horarios,link,...}],total})
  "Obtener Comercio Confirmado" (nodo_flow → sub-flow "confirm_choice"),
  expandido en runtime con prefijo `obtener_comercio_confirmado::`:
  obtener_comercio_confirmado::node_choose     llm        → state.propuesta_actual
                                                           ("nombre ||| datos" o "SIN_RESULTADOS")
  obtener_comercio_confirmado::node_check      llm        "Verificar confirmación" → state.comercio_confirmado
  obtener_comercio_confirmado::node_condition  condition  found | pedir_mas_info | not_found (max_visits=3)
  responder_comercio_encontrado  nodo_flow  (mensaje fijo, found)
  disculpar_sin_comercio         nodo_flow  (mensaje fijo, not_found — agotado o sin resultados)

  Rama "producto" (mismo patrón B, misma migración 2026-07-21):
  node_1783949755356  fetch_http        "Buscar producto" → state.producto_luganense
                                        (JSON crudo {results:[{nombre,categoria,
                                        descripcion,precio,proveedor,contactos,
                                        link,...}],total})
  "Obtener Producto Confirmado" (nodo_flow → sub-flow "confirm_choice"),
  expandido en runtime con prefijo `obtener_producto_confirmado::`:
  obtener_producto_confirmado::node_choose     llm        → state.propuesta_actual
                                                           ("nombre ||| datos" o "SIN_RESULTADOS")
  obtener_producto_confirmado::node_check      llm        "Verificar confirmación" → state.producto_confirmado
  obtener_producto_confirmado::node_condition  condition  found | pedir_mas_info | not_found (max_visits=3)
  responder_producto_encontrado  nodo_flow  (mensaje fijo, found)
  disculpar_sin_producto         nodo_flow  (mensaje fijo, not_found — agotado o sin resultados)

  Rama "noticias" (rediseñada 2026-07-20/21 — antes tiraba hasta 3 resultados
  en UN solo mensaje sin confirmar nada; ahora itera de a una publicación,
  con link, hasta que el vecino confirma cuál buscaba o se agotan los
  intentos, igual que "servicio" confirma un rubro):
  expandir_consulta        llm         → state.query
  node_1783693824414       fetch_http  "Buscar noticias" → state.context (lista de
                                        resultados crudos, uno por término de
                                        `query`, cada uno {results:[{url,text,...}],total})

  "Obtener Noticia Confirmada" (nodo_flow → sub-flow reusable "confirm_choice",
  patrón B: propone un candidato de una lista, pregunta, si rechaza propone
  otro — ver docstring de confirm_choice). Expandido en runtime con prefijo
  `obtener_noticia_confirmada::`:
  obtener_noticia_confirmada::node_choose        llm        "Elegir propuesta" → state.propuesta_actual
                                                             ("url ||| resumen" o "SIN_RESULTADOS")
  obtener_noticia_confirmada::node_check_empty   condition  ¿SIN_RESULTADOS? → vacio | hay_candidato
  obtener_noticia_confirmada::node_track         set_state  acumula urls ya propuestas (dedup entre rondas)
  obtener_noticia_confirmada::node_ask           llm        arma el mensaje que presenta la publicación + link
  obtener_noticia_confirmada::node_send          send_message
  obtener_noticia_confirmada::node_wait          wait_user
  obtener_noticia_confirmada::node_check         llm        "Verificar confirmación" → state.noticia_confirmada (o UNCLEAR)
  obtener_noticia_confirmada::node_condition     condition  found (confirmó) | pedir_mas_info (rechazó, vuelve a
                                                             node_choose) | not_found (max_visits=3 o SIN_RESULTADOS)

  responder_noticia_encontrada  send_message  (mensaje fijo, found)
  disculpar_sin_noticia         send_message  (mensaje fijo, not_found — agotado o sin resultados)
  end_conv_noticias             end_conversation

  Rama "servicio" (rediseñada 2026-07-14, 2ª vuelta — tras feedback: ya no se
  confirma el nombre propio de un prestador puntual, se confirma el RUBRO del
  servicio primero. Motivo: el candidato que devuelve Luganense es SIEMPRE el
  que ellos resuelven como mejor opción para ese rubro (no hay 2 para elegir
  de nuestro lado), así que "confirmar" un nombre propio no tenía sentido —
  lo que puede estar mal es el RUBRO que entendimos de la necesidad del
  vecino. Luganense expuso `GET /api/directorio/rubros?tipo=servicios&q=`
  (matching por texto libre sobre la necesidad, mismo motor que `/buscar` y
  `/candidato`) para poder confirmar contra una lista real de rubros, sin
  inventar ninguno. Recién con el rubro confirmado se llama a
  `/candidato?q=<rubro>` para resolver el prestador puntual — un solo llamado,
  después de la confirmación, no antes.

  Migrado 2026-07-20 a "Obtener Rubro Confirmado" (nodo_flow → sub-flow
  reusable "confirm_choice", patrón B: propone un candidato de una lista,
  pregunta, si rechaza propone otro de la misma lista — mismo patrón que
  noticias más abajo). Antes eran 5 nodos hardcodeados (elegir_rubro,
  "Confirmar Rubro" send_message, wait_user, "Obtener rubro confirmado" llm,
  "Confirmó Rubro?" condition); ahora es UN nodo_flow expandido en runtime con
  prefijo `obtener_rubro_confirmado::`:
  buscar_rubros        fetch_http       GET /api/directorio/rubros?tipo=servicios&q={{necesidad}}
                                         → state.rubros_luganense (JSON crudo: {rubros:[{categoria,label}],total})
                                         + extract_fields: state.rubros_total
  rubros_encontrados_cond condition     ¿rubros_total == "0"? → sin_resultados : encontrado
                                         sin_resultados → disculpar_sin_servicio_msg → end_conv_fail

  obtener_rubro_confirmado::node_choose      llm        "Elegir propuesta" — grounded ÚNICAMENTE a
                                                         `rubros_luganense` (nunca inventa un rubro fuera de
                                                         la lista) → state.propuesta_actual (el "label" elegido).
                                                         Si ya se había propuesto antes y no fue confirmado, elige
                                                         otro distinto de la misma lista (si hay más de una opción).
  obtener_rubro_confirmado::node_send         send_message  "¿Es este el tipo de servicio que necesitás: RUBRO?"
  obtener_rubro_confirmado::node_wait         wait_user
  obtener_rubro_confirmado::node_check        llm        "Verificar confirmación" → state.rubro_elegido (el
                                                         output final expuesto del nodo_flow) o UNCLEAR
  obtener_rubro_confirmado::node_condition    condition  found (confirmó) | pedir_mas_info (rechazó, vuelve a
                                                         node_choose — no hace falta re-pegarle a `/rubros`, la
                                                         necesidad no cambió) | not_found (max_visits=3, agotado)
                                                         found → buscar_servicio (recién ahí se resuelve el
                                                         candidato puntual); not_found → disculpar_rubro_agotado
                                                         → end_conv_fail.
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
  Migrado 2026-07-20 a "Obtener Dirección Confirmada" (nodo_flow → sub-flow
  reusable "get_data", el mismo patrón A que "Obtener Necesidad" más arriba —
  acá calzó 1:1 sin ajustes, porque el orden ya era "revisar si ya está el
  dato → si no, preguntar" desde antes de la migración). Antes eran 5 nodos
  hardcodeados; ahora es UN nodo_flow expandido en runtime con prefijo
  `obtener_direccion_confirmada::`:
  obtener_direccion_confirmada::node_1783192800831  llm        "Identificar dato" ("Obtener dirección")
                                                     → state.direccion (o UNCLEAR)
  obtener_direccion_confirmada::node_1783356000392  condition  "Condición dato identificado" → found | pedir_mas_info | not_found
                                                     (antes tiene_direccion | sin_direccion | agotado, max_visits=3)
  set_direccion       set_state         → state.direccion (bug real 2026-07-10: usaba {{message}}, roto —
                                         fijado a {{conversation.last}} en su momento; hoy es un copy-through
                                         redundante {{direccion}}={{direccion}}, inofensivo, porque el nodo_flow
                                         ya escribe `direccion` directo vía `output`)
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
import json
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
# "Obtener Necesidad" — nodo_flow → sub-flow "get_data" (patrón A), expandido
# en runtime con prefijo "node_1784503628687::" (el id del propio nodo_flow).
N_OBTENER_NECESIDAD = "node_1784503628687::node_1783192800831"  # llm "Identificar dato" → state.necesidad
N_CONDICION = "node_1784503628687::node_1783356000392"  # condition → found | pedir_mas_info | not_found
N_ELEGIR_MOSTRADOR = "node_1783192962168"

N_COMERCIO_FETCH = "node_1783949463710"
# "Obtener Comercio Confirmado" — nodo_flow → sub-flow "confirm_choice"
# (patrón B, migrado 2026-07-21 desde la vieja llm "Armar mensaje referencia
# de comercio" + "Cerrar conversación" sueltas — mismo patrón que noticias),
# expandido en runtime con prefijo `obtener_comercio_confirmado::`.
N_COMERCIO_ELEGIR = "obtener_comercio_confirmado::node_choose"  # llm → state.propuesta_actual ("nombre ||| datos" o SIN_RESULTADOS)
N_COMERCIO_CONFIRMAR = "obtener_comercio_confirmado::node_check"  # llm "Verificar confirmación" → state.comercio_confirmado
N_COMERCIO_CONDICION = "obtener_comercio_confirmado::node_condition"  # condition → found | pedir_mas_info | not_found
N_RESPONDER_COMERCIO_ENCONTRADO = "responder_comercio_encontrado::node_send"  # mensaje fijo (sin LLM) si found
N_END_CONV_COMERCIO_FOUND = "responder_comercio_encontrado::node_close"
N_DISCULPAR_SIN_COMERCIO = "disculpar_sin_comercio::node_send"  # mensaje fijo (sin LLM) si not_found (agotado o sin resultados)
N_END_CONV_COMERCIO_NOTFOUND = "disculpar_sin_comercio::node_close"

N_PRODUCTO_FETCH = "node_1783949755356"
# "Obtener Producto Confirmado" — mismo patrón/migración que comercio arriba,
# expandido en runtime con prefijo `obtener_producto_confirmado::`.
N_PRODUCTO_ELEGIR = "obtener_producto_confirmado::node_choose"  # llm → state.propuesta_actual ("nombre ||| datos" o SIN_RESULTADOS)
N_PRODUCTO_CONFIRMAR = "obtener_producto_confirmado::node_check"  # llm "Verificar confirmación" → state.producto_confirmado
N_PRODUCTO_CONDICION = "obtener_producto_confirmado::node_condition"  # condition → found | pedir_mas_info | not_found
N_RESPONDER_PRODUCTO_ENCONTRADO = "responder_producto_encontrado::node_send"  # mensaje fijo (sin LLM) si found
N_END_CONV_PRODUCTO_FOUND = "responder_producto_encontrado::node_close"
N_DISCULPAR_SIN_PRODUCTO = "disculpar_sin_producto::node_send"  # mensaje fijo (sin LLM) si not_found (agotado o sin resultados)
N_END_CONV_PRODUCTO_NOTFOUND = "disculpar_sin_producto::node_close"

N_NOTICIAS_EXPANDIR = "expandir_consulta"
N_NOTICIAS_FETCH = "node_1783693824414"
# "Obtener Noticia Confirmada" — nodo_flow → sub-flow "confirm_choice" (patrón
# B), expandido en runtime con prefijo "obtener_noticia_confirmada::".
N_NOTICIAS_ELEGIR = "obtener_noticia_confirmada::node_choose"  # llm → state.propuesta_actual ("url ||| resumen" o SIN_RESULTADOS)
N_NOTICIAS_CONFIRMAR = "obtener_noticia_confirmada::node_check"  # llm "Verificar confirmación" → state.noticia_confirmada
N_NOTICIAS_CONDICION = "obtener_noticia_confirmada::node_condition"  # condition → found | pedir_mas_info | not_found
# "responder_noticia_encontrada" / "disculpar_sin_noticia" pasaron a ser
# instancias de "reply_and_close" (refactor 2026-07-21, ver backup
# "pre-reply_and_close-refactor") — ya no hay un nodo "end_conv_noticias"
# suelto, el cierre (send + end_conversation) vive ADENTRO del propio
# nodo_flow, expandido en runtime con "::node_send"/"::node_close".
N_RESPONDER_NOTICIA_ENCONTRADA = "responder_noticia_encontrada::node_send"  # mensaje fijo (sin LLM) si found
N_END_CONV_NOTICIAS_FOUND = "responder_noticia_encontrada::node_close"
N_DISCULPAR_SIN_NOTICIA = "disculpar_sin_noticia::node_send"  # mensaje fijo (sin LLM) si not_found (agotado o sin resultados)
N_END_CONV_NOTICIAS_NOTFOUND = "disculpar_sin_noticia::node_close"

# "Obtener Dirección Confirmada" — nodo_flow → sub-flow "get_data" (patrón A),
# expandido en runtime con prefijo "obtener_direccion_confirmada::".
N_OBTENER_DIRECCION = "obtener_direccion_confirmada::node_1783192800831"  # llm "Identificar dato" → state.direccion
N_VALIDAR_DIRECCION = "obtener_direccion_confirmada::node_1783356000392"  # condition → found | pedir_mas_info | not_found (antes tiene_direccion/sin_direccion/agotado, max_visits=3)
N_BUSCAR_RUBROS = "buscar_rubros"  # GET /rubros?q={{necesidad}}, route_output → encontrado/error, sin Condition aparte
# "Obtener Rubro Confirmado" — nodo_flow → sub-flow "confirm_choice" (patrón
# B, migrado 2026-07-20 desde 5 nodos hardcodeados), expandido en runtime con
# prefijo "obtener_rubro_confirmado::".
N_ELEGIR_RUBRO = "obtener_rubro_confirmado::node_choose"  # llm grounded a rubros_luganense → state.propuesta_actual
N_CONFIRMAR_RUBRO = "obtener_rubro_confirmado::node_send"  # send_message "¿Es este el tipo de servicio...?"
N_OBTENER_RUBRO_CONFIRMADO = "obtener_rubro_confirmado::node_check"  # llm → state.rubro_elegido (o UNCLEAR)
N_CONFIRMO_RUBRO = "obtener_rubro_confirmado::node_condition"  # condition → found | pedir_mas_info | not_found
N_BUSCAR_SERVICIO = "buscar_servicio"  # GET /candidato?q={{rubro_elegido}}, extract_fields, sin LLM — corre tras confirmar el rubro
N_SERVICIO_ENCONTRADO_COND = "servicio_encontrado_cond"  # ¿state.servicio no vacío? → encontrado | sin_resultados
N_DISCULPAR_SIN_SERVICIO = "disculpar_sin_servicio_msg"  # mensaje fijo (sin LLM) si sin_resultados
N_DISCULPAR_RUBRO_AGOTADO = "disculpar_rubro_agotado"  # mensaje fijo (sin LLM) si se agotan los 3 intentos de confirmar rubro
N_NOTIFICAR_TRABAJADOR = "notificar_trabajador"
N_RESPONDER_SERVICIO = "responder_vecino_oficio"
N_SET_DIRECCION = "set_direccion"
# El cierre de "servicio" (antes "end_conv_ok") NO quedó envuelto en
# "reply_and_close" como los demás — sigue siendo un send_message + un
# end_conversation sueltos, pero con un id autogenerado (sin slug propio
# puesto en el editor) en vez de "end_conv_ok". Frágil si se vuelve a tocar
# ese nodo en el editor (el id cambiaría) — vale la pena pedirle a quien
# haga el próximo pase por el editor que le ponga un id/nombre estable.
N_END_CONV_OK = "node_1784655913105"
# "end_conv_scope" y "end_conv_fail" sí son "reply_and_close" (mismo
# refactor 2026-07-21) — cierre real en "<id>::node_close".
N_END_CONV_SCOPE = "end_conv_scope::node_close"
N_END_CONV_FAIL = "end_conv_fail::node_close"


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


def _found_real_news(conv: SimConversation, fetch_node_id: str) -> Check:
    """
    Assert real (no solo "el nodo corrió", ver bug real 2026-07-20: el fetch
    de noticias corría OK y el test lo marcaba en verde aunque devolviera 0
    resultados SIEMPRE — porque el `query` armado por `expandir_consulta`
    llegaba roto a `/api/noticias` (lista multilínea sin trocear en el fetch,
    o líneas con numeración/comillas que ya no matcheaban ningún substring
    literal del post). El caso "Hola, qué se sabe del corte de luz en Lugano"
    tiene datos reales en Luganense (ver Neon `noticias`, page_id=luganense,
    posts con "corte de luz" en el texto) — si la búsqueda real no encuentra
    NADA acá, es un bug de integración, no "el barrio no tiene esa noticia".
    """
    raw = conv.state_field(fetch_node_id, "context")
    responses = raw if isinstance(raw, list) else [raw]
    total_results = 0
    for r in responses:
        if not r:
            continue
        try:
            parsed = json.loads(r)
        except (json.JSONDecodeError, TypeError):
            continue
        total_results += len(parsed.get("results") or [])
    return _c(
        "Encontró al menos una publicación real sobre el corte de luz en Luganense",
        total_results > 0,
        detail=f"total_results={total_results} raw={responses!r}" if total_results == 0 else "",
    )


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


def _no_separator_leak(turns: list[tuple[str, str]]) -> Check:
    """Assert real (estructural, no de redacción): ningún reply del bot debe
    filtrar el separador técnico "|||" que usa `confirm_choice` para
    codificar "identificador ||| resumen" en `propuesta_actual` — es un dato
    interno entre `node_choose` y `node_ask`, nunca algo para mostrarle al
    vecino (bug real encontrado 2026-07-21 al migrar comercio/producto: el
    LLM de `node_ask` a veces copia el string crudo en vez de redactarlo)."""
    filtrados = [text for role, text in turns if role == "bot" and "|||" in (text or "")]
    return _c(
        "Ningún reply del bot filtró el separador técnico \"|||\" (siempre redactado en prosa)",
        not filtrados, detail=str(filtrados) if filtrados else "",
    )


def _total_real_directorio(conv: SimConversation, fetch_node_id: str, field: str) -> int:
    """Análogo a `_total_real_news`/`_total_real_news` pero para los fetch
    de directorio (comercio/producto) — estos NO usan `array_input` (una
    sola llamada), así que `state_field` devuelve un único string JSON crudo,
    no una lista de strings."""
    raw = conv.state_field(fetch_node_id, field)
    if not raw:
        return 0
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return 0
    return len(parsed.get("results") or [])


# ─── 1. Comercio — con loop de aclaración + resiliencia a mensaje ambiguo,
#        más el loop de confirmación de "confirm_choice" (migrado 2026-07-21,
#        mismo patrón que "noticias": propone un comercio, si el vecino
#        rechaza propone otro sin repetir, hasta que confirma) ──────────────

async def _run_comercio() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r1 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r1))
        r2 = await conv.send_and_wait("asdfgh")
        turns.append(("user", "asdfgh")); turns.append(("bot", r2))
        propone_1 = await conv.send_and_wait("busco una ferretería")
        turns.append(("user", "busco una ferretería")); turns.append(("bot", propone_1))

        m4 = "no, ese no es"
        propone_2 = await conv.send_and_wait(m4)
        turns.append(("user", m4)); turns.append(("bot", propone_2))

        m5 = "sí, ese es"
        reply = await conv.send_and_wait(m5)
        turns.append(("user", m5)); turns.append(("bot", reply))

        checks = [
            _log("Turno 1 (\"hola\", ambiguo): clasificación de necesidad",
                 detail=f"necesidad={conv.state_field(N_OBTENER_NECESIDAD, 'necesidad', occurrence=0)!r}"),
            _log("Turno 1: rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION, occurrence=0)!r}"),
            _c("Turno 1: el bot respondió pidiendo aclaración (no vacío)", bool(r1)),
            _c("Turno 2 (\"asdfgh\", ambiguo de nuevo): el flow no se rompió, siguió respondiendo (no vacío)", bool(r2)),
        ]
        checks.append(_log("Turno 3: rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"))
        checks.append(_ran_all(
            "Turno 3: pasó por el fetch al directorio y propuso un comercio",
            conv, N_COMERCIO_FETCH, N_COMERCIO_ELEGIR,
        ))
        checks.append(_c("Turno 3: el bot propuso algo (no vacío)", bool(propone_1)))
        propuesta_1a = conv.state_field(N_COMERCIO_ELEGIR, "propuesta_actual", occurrence=0)
        propuesta_2a = conv.state_field(N_COMERCIO_ELEGIR, "propuesta_actual", occurrence=1)
        checks.append(_log("Comercio propuesto (1ª propuesta)", detail=f"{propuesta_1a!r}"))
        checks.append(_log("Rama de \"Confirmó la propuesta?\" (turno 4, rechaza)",
                            detail=f"branch={conv.branch_taken(N_COMERCIO_CONDICION, occurrence=0)!r}"))
        checks.append(_ran_all(
            "Turno 4: volvió a proponer tras el rechazo (2ª ejecución, sin re-pegarle al fetch)",
            conv, N_COMERCIO_ELEGIR,
        ))
        checks.append(_log("Comercio propuesto (2ª propuesta, tras el rechazo)", detail=f"{propuesta_2a!r}"))
        total_results = _total_real_directorio(conv, N_COMERCIO_FETCH, "comercio_luganense")
        if total_results > 1:
            checks.append(_c(
                "No repitió el mismo comercio en la 2ª propuesta habiendo más de 1 candidato (dedup de confirm_choice)",
                propuesta_2a != propuesta_1a,
                detail=f"1ª={propuesta_1a!r} 2ª={propuesta_2a!r} total_results={total_results}",
            ))
        checks.append(_log("Rama de \"Confirmó la propuesta?\" (turno 5, confirma)",
                            detail=f"branch={conv.branch_taken(N_COMERCIO_CONDICION, occurrence=1)!r}"))
        checks += _infra_checks(conv, reply)
        checks.append(_ran_all(
            "Turno 5: confirmó el comercio y cerró por la rama de éxito (found)",
            conv, N_COMERCIO_CONFIRMAR, N_RESPONDER_COMERCIO_ENCONTRADO, N_END_CONV_COMERCIO_FOUND,
        ))
        checks.append(_no_separator_leak(turns))
    return ScenarioResult(turns, checks)


# ─── 1b. (único camino infeliz de comercio) Agotamiento tras 3 rechazos ──────
#         Insistencia del vecino: rechaza TODAS las propuestas de comercio
#         (3 intentos, max_visits de "confirm_choice", ver N_COMERCIO_CONDICION)
#         sin confirmar ninguna — mismo camino infeliz que noticias
#         (`_run_noticias_agotado`), aplicado a la rama migrada de comercio.

async def _run_comercio_agotado() -> ScenarioResult:
    """
    Camino infeliz de la rama comercio (migrada 2026-07-21 al patrón B
    "confirm_choice"): el vecino insiste rechazando las 3 propuestas seguidas
    sin confirmar ninguna — el flow debe cerrar solo igual, por la rama de
    disculpa (`not_found` → disculpar_sin_comercio), no quedarse colgado ni
    repetir la misma propuesta indefinidamente.
    """
    turns = []
    async with SimConversation(BOT_ID) as conv:
        m1 = "busco una ferretería"
        last_reply = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", last_reply))

        rechazos = ["no, ese no es", "no, tampoco es ese", "no, ese tampoco"]
        for msg in rechazos:
            last_reply = await conv.send_and_wait(msg)
            turns.append(("user", msg)); turns.append(("bot", last_reply))

        checks = [
            _ran_all(
                "Propuso al menos una vez antes de agotar los intentos",
                conv, N_COMERCIO_FETCH, N_COMERCIO_ELEGIR,
            ),
            _log("Rama de \"Confirmó la propuesta?\" tras agotar reintentos (esperado: not_found)",
                 detail=f"branch={conv.branch_taken(N_COMERCIO_CONDICION)!r}"),
        ]
        visitas = conv.state_field(N_COMERCIO_CONDICION, "_visits_" + N_COMERCIO_CONDICION)
        checks.append(_c(
            f"El contador de reintentos (_visits_{N_COMERCIO_CONDICION}) llegó exactamente a 3 "
            "(mecánica del engine — max_visits, no una decisión de contenido del LLM)",
            visitas == 3, detail=f"visits={visitas!r}",
        ))
        checks += _infra_checks(conv, last_reply)
        checks.append(_ran_all(
            "Cerró por la rama de disculpa (disculpar_sin_comercio), no se quedó colgado",
            conv, N_DISCULPAR_SIN_COMERCIO, N_END_CONV_COMERCIO_NOTFOUND,
        ))
        checks.append(_no_separator_leak(turns))
    return ScenarioResult(turns, checks)


# ─── 2. Comercio sin rubro explícito (Kiosco Don Jorge) — resolución de la
#        necesidad en 1 turno, más un turno de confirmación (patrón B) ──────

async def _run_comercio_sin_rubro() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        msg = "Hola, ¿podés decirme el teléfono de Kiosco Don Jorge?"
        propone = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", propone))

        m2 = "sí, es ese"
        reply = await conv.send_and_wait(m2)
        turns.append(("user", m2)); turns.append(("bot", reply))

        checks = [
            _log("¿Resolvió la necesidad en el PRIMER turno, sin pedir aclaración?",
                 detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
            _log("Rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"),
        ]
        checks.append(_ran_all(
            "Turno 1: pasó por el fetch al directorio y propuso un comercio",
            conv, N_COMERCIO_FETCH, N_COMERCIO_ELEGIR,
        ))
        checks.append(_c("Turno 1: el bot propuso algo (no vacío)", bool(propone)))
        checks.append(_log("Comercio propuesto", detail=f"{conv.state_field(N_COMERCIO_ELEGIR, 'propuesta_actual', occurrence=0)!r}"))
        checks.append(_log("Rama de \"Confirmó la propuesta?\" (turno 2, confirma)",
                            detail=f"branch={conv.branch_taken(N_COMERCIO_CONDICION)!r}"))
        checks += _infra_checks(conv, reply)
        checks.append(_ran_all(
            "Turno 2: confirmó el comercio y cerró por la rama de éxito (found)",
            conv, N_COMERCIO_CONFIRMAR, N_RESPONDER_COMERCIO_ENCONTRADO, N_END_CONV_COMERCIO_FOUND,
        ))
        checks.append(_no_separator_leak(turns))
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
#
# Migrado 2026-07-21 al mismo patrón B ("confirm_choice") que comercio/
# noticias — ahora hace falta confirmar la propuesta, y (a pedido de
# Luganense, que sumó 2 productos más de QA en la categoría iluminación el
# mismo día — ver `las agent inject Luganense`) "focos LED" tiene 3
# candidatos reales, así que este escenario ejercita el mismo camino que
# comercio: 1ª propuesta rechazada → 2ª propuesta (distinta, sin repetir) →
# confirmada.

async def _run_producto() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        msg = "Hola, necesito comprar unos focos LED para mi casa"
        propone_1 = await conv.send_and_wait(msg)
        turns.append(("user", msg)); turns.append(("bot", propone_1))

        m2 = "no, ese no es"
        propone_2 = await conv.send_and_wait(m2)
        turns.append(("user", m2)); turns.append(("bot", propone_2))

        m3 = "sí, ese es"
        reply = await conv.send_and_wait(m3)
        turns.append(("user", m3)); turns.append(("bot", reply))

        checks = [
            _log("Rama tomada por la Condición", detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
        ]
        checks.append(_log("Rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"))
        checks.append(_ran_all(
            "Turno 1: pasó por el fetch de productos y propuso uno",
            conv, N_PRODUCTO_FETCH, N_PRODUCTO_ELEGIR,
        ))
        checks.append(_c("Turno 1: el bot propuso algo (no vacío)", bool(propone_1)))
        propuesta_1a = conv.state_field(N_PRODUCTO_ELEGIR, "propuesta_actual", occurrence=0)
        propuesta_2a = conv.state_field(N_PRODUCTO_ELEGIR, "propuesta_actual", occurrence=1)
        checks.append(_log("Producto propuesto (1ª propuesta)", detail=f"{propuesta_1a!r}"))
        checks.append(_log("Rama de \"Confirmó la propuesta?\" (turno 2, rechaza)",
                            detail=f"branch={conv.branch_taken(N_PRODUCTO_CONDICION, occurrence=0)!r}"))
        checks.append(_ran_all(
            "Turno 2: volvió a proponer tras el rechazo (2ª ejecución, sin re-pegarle al fetch)",
            conv, N_PRODUCTO_ELEGIR,
        ))
        checks.append(_log("Producto propuesto (2ª propuesta, tras el rechazo)", detail=f"{propuesta_2a!r}"))
        total_results = _total_real_directorio(conv, N_PRODUCTO_FETCH, "producto_luganense")
        if total_results > 1:
            checks.append(_c(
                "No repitió el mismo producto en la 2ª propuesta habiendo más de 1 candidato (dedup de confirm_choice)",
                propuesta_2a != propuesta_1a,
                detail=f"1ª={propuesta_1a!r} 2ª={propuesta_2a!r} total_results={total_results}",
            ))
        checks.append(_log("Rama de \"Confirmó la propuesta?\" (turno 3, confirma)",
                            detail=f"branch={conv.branch_taken(N_PRODUCTO_CONDICION, occurrence=1)!r}"))
        checks += _infra_checks(conv, reply)
        checks.append(_ran_all(
            "Turno 3: confirmó el producto y cerró por la rama de éxito (found)",
            conv, N_PRODUCTO_CONFIRMAR, N_RESPONDER_PRODUCTO_ENCONTRADO, N_END_CONV_PRODUCTO_FOUND,
        ))
        checks.append(_no_separator_leak(turns))
    return ScenarioResult(turns, checks)


# ─── 3b. (único camino infeliz de producto) Agotamiento tras 3 rechazos ──────
#         Insistencia del vecino: rechaza TODAS las propuestas de producto
#         (3 intentos, max_visits de "confirm_choice", ver N_PRODUCTO_CONDICION)
#         sin confirmar ninguna — mismo camino infeliz que noticias/comercio,
#         aplicado a producto. "Focos LED" tiene 3 candidatos reales (ver
#         docstring de `_run_producto` más arriba), así que las 3 propuestas
#         pueden ser distintas entre sí (sin necesidad de repetir por falta
#         de opciones) — el flow debe cerrar solo igual por la rama de
#         disculpa, sin quedarse colgado ni reintentar indefinidamente.

async def _run_producto_agotado() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        m1 = "Hola, necesito comprar unos focos LED para mi casa"
        last_reply = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", last_reply))

        rechazos = ["no, ese no es", "no, tampoco es ese", "no, ese tampoco"]
        for msg in rechazos:
            last_reply = await conv.send_and_wait(msg)
            turns.append(("user", msg)); turns.append(("bot", last_reply))

        checks = [
            _ran_all(
                "Propuso al menos una vez antes de agotar los intentos",
                conv, N_PRODUCTO_FETCH, N_PRODUCTO_ELEGIR,
            ),
            _log("Rama de \"Confirmó la propuesta?\" tras agotar reintentos (esperado: not_found)",
                 detail=f"branch={conv.branch_taken(N_PRODUCTO_CONDICION)!r}"),
        ]
        visitas = conv.state_field(N_PRODUCTO_CONDICION, "_visits_" + N_PRODUCTO_CONDICION)
        checks.append(_c(
            f"El contador de reintentos (_visits_{N_PRODUCTO_CONDICION}) llegó exactamente a 3 "
            "(mecánica del engine — max_visits, no una decisión de contenido del LLM)",
            visitas == 3, detail=f"visits={visitas!r}",
        ))
        checks += _infra_checks(conv, last_reply)
        checks.append(_ran_all(
            "Cerró por la rama de disculpa (disculpar_sin_producto), no se quedó colgado",
            conv, N_DISCULPAR_SIN_PRODUCTO, N_END_CONV_PRODUCTO_NOTFOUND,
        ))
        checks.append(_no_separator_leak(turns))
    return ScenarioResult(turns, checks)


# ─── 4. Noticias — itera de a una publicación hasta que el vecino confirma ───
#
# Rediseño 2026-07-20/21: antes tiraba hasta 3 resultados en UN solo mensaje,
# sin confirmar nada. Ahora usa el mismo patrón B ("confirm_choice") que
# "servicio" usa para el rubro: propone UNA publicación con su link, y si el
# vecino dice que no es esa, propone otra (sin repetir, ver `N_NOTICIAS_ELEGIR`
# más abajo) hasta que confirma o se agotan los 3 intentos (ver
# `_run_noticias_agotado`). Este escenario ejercita el camino feliz completo:
# 1ª propuesta rechazada → 2ª propuesta (distinta) confirmada.

def _total_real_news(conv: SimConversation, fetch_node_id: str = None) -> int:
    """Cuenta resultados reales devueltos por el fetch de noticias (ver
    `_found_real_news` — misma lógica de parseo, expuesta acá para poder
    decidir cuántas propuestas distintas son esperables antes de aserter
    dedup en `_run_noticias`)."""
    raw = conv.state_field(fetch_node_id or N_NOTICIAS_FETCH, "context")
    responses = raw if isinstance(raw, list) else [raw]
    total = 0
    for r in responses:
        if not r:
            continue
        try:
            parsed = json.loads(r)
        except (json.JSONDecodeError, TypeError):
            continue
        total += len(parsed.get("results") or [])
    return total


async def _run_noticias() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        m1 = "Hola, qué se sabe del corte de luz en Lugano"
        propone_1 = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", propone_1))

        m2 = "no, esa no es"
        propone_2 = await conv.send_and_wait(m2)
        turns.append(("user", m2)); turns.append(("bot", propone_2))

        m3 = "sí, esa es"
        reply = await conv.send_and_wait(m3)
        turns.append(("user", m3)); turns.append(("bot", reply))

        checks = [
            _log("Rama tomada por la Condición (necesidad)", detail=f"branch={conv.branch_taken(N_CONDICION)!r}"),
            _log("Rama tomada por Elegir Mostrador", detail=f"branch={conv.branch_taken(N_ELEGIR_MOSTRADOR)!r}"),
            _ran_all(
                "Turno 1: expandió la consulta, buscó noticias reales y propuso una publicación",
                conv, N_NOTICIAS_EXPANDIR, N_NOTICIAS_FETCH, N_NOTICIAS_ELEGIR,
            ),
            _found_real_news(conv, N_NOTICIAS_FETCH),
            _c("Turno 1: el bot propuso algo (no vacío)", bool(propone_1)),
        ]
        propuesta_1a = conv.state_field(N_NOTICIAS_ELEGIR, "propuesta_actual", occurrence=0)
        propuesta_2a = conv.state_field(N_NOTICIAS_ELEGIR, "propuesta_actual", occurrence=1)
        checks.append(_log("Publicación propuesta (1ª propuesta)", detail=f"{propuesta_1a!r}"))
        checks.append(_log("Rama de \"Confirmó la propuesta?\" (turno 2, rechaza)",
                            detail=f"branch={conv.branch_taken(N_NOTICIAS_CONDICION, occurrence=0)!r}"))
        checks.append(_ran_all(
            "Turno 2: volvió a proponer tras el rechazo (2ª ejecución, sin re-pegarle al fetch)",
            conv, N_NOTICIAS_ELEGIR,
        ))
        checks.append(_log("Publicación propuesta (2ª propuesta, tras el rechazo)", detail=f"{propuesta_2a!r}"))
        total_results = _total_real_news(conv)
        if total_results > 1:
            # Solo assertable si había más de 1 publicación real candidata —
            # con una sola disponible, "confirm_choice" repite la misma a
            # propósito (no hay otra opción, ver su docstring).
            checks.append(_c(
                "No repitió la misma publicación en la 2ª propuesta habiendo más de 1 candidata (dedup de confirm_choice)",
                propuesta_2a != propuesta_1a,
                detail=f"1ª={propuesta_1a!r} 2ª={propuesta_2a!r} total_results={total_results}",
            ))
        checks.append(_log("Rama de \"Confirmó la propuesta?\" (turno 3, confirma)",
                            detail=f"branch={conv.branch_taken(N_NOTICIAS_CONDICION, occurrence=1)!r}"))
        checks += _infra_checks(conv, reply)
        checks.append(_ran_all(
            "Turno 3: confirmó la publicación y cerró por la rama de éxito (found)",
            conv, N_NOTICIAS_CONFIRMAR, N_RESPONDER_NOTICIA_ENCONTRADA, N_END_CONV_NOTICIAS_FOUND,
        ))
        checks.append(_no_separator_leak(turns))
    return ScenarioResult(turns, checks)


# ─── 4b. (único camino infeliz de noticias) Agotamiento tras 3 rechazos ──────

async def _run_noticias_agotado() -> ScenarioResult:
    """
    Camino infeliz del nuevo loop de noticias: el vecino rechaza TODAS las
    propuestas (3 intentos, max_visits de la condición interna de
    "confirm_choice", ver `N_NOTICIAS_CONDICION`) sin confirmar ninguna — el
    flow debe cerrar solo igual, por la rama de disculpa con el link de
    Facebook como fallback (`not_found` → disculpar_sin_noticia →
    end_conv_noticias), no quedarse colgado ni repetir el mensaje de "no
    encontré nada" (eso sería el bug real encontrado y arreglado 2026-07-20/21:
    antes el nodo que arma el mensaje de propuesta podía confundirse y
    devolver el mensaje de "sin resultados" aunque sí hubiera una publicación
    real para proponer — ver el chequeo de "propuesta real" turno a turno acá
    abajo, no solo el cierre final).
    """
    turns = []
    async with SimConversation(BOT_ID) as conv:
        m1 = "Hola, qué se sabe del corte de luz en Lugano"
        last_reply = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", last_reply))

        rechazos = ["no, esa no es", "no, tampoco es esa", "no, esa tampoco"]
        for msg in rechazos:
            last_reply = await conv.send_and_wait(msg)
            turns.append(("user", msg)); turns.append(("bot", last_reply))

        checks = [
            _ran_all(
                "Propuso al menos una vez antes de agotar los intentos",
                conv, N_NOTICIAS_EXPANDIR, N_NOTICIAS_FETCH, N_NOTICIAS_ELEGIR,
            ),
            _found_real_news(conv, N_NOTICIAS_FETCH),
            _log("Rama de \"Confirmó la propuesta?\" tras agotar reintentos (esperado: not_found)",
                 detail=f"branch={conv.branch_taken(N_NOTICIAS_CONDICION)!r}"),
        ]
        visitas = conv.state_field(N_NOTICIAS_CONDICION, "_visits_" + N_NOTICIAS_CONDICION)
        checks.append(_c(
            f"El contador de reintentos (_visits_{N_NOTICIAS_CONDICION}) llegó exactamente a 3 "
            "(mecánica del engine — max_visits, no una decisión de contenido del LLM)",
            visitas == 3, detail=f"visits={visitas!r}",
        ))
        checks += _infra_checks(conv, last_reply)
        checks.append(_ran_all(
            "Cerró por la rama de disculpa (disculpar_sin_noticia → end_conv_noticias), no se quedó colgado",
            conv, N_DISCULPAR_SIN_NOTICIA, N_END_CONV_NOTICIAS_NOTFOUND,
        ))
        checks.append(_no_separator_leak(turns))
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
        # así el 1er rubro propuesto por "Elegir propuesta" (N_ELEGIR_RUBRO)
        # puede no ser el que el vecino tenía en mente, y el rechazo +
        # corrección tiene sentido real
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
                conv, N_BUSCAR_RUBROS, N_ELEGIR_RUBRO, N_CONFIRMAR_RUBRO,
            ),
            _log("Rubros que matchearon la necesidad", detail=f"{conv.state_field(N_BUSCAR_RUBROS, 'rubros_luganense', occurrence=0)!r}"),
            _log("Rubro ofrecido (1ª propuesta)", detail=f"{conv.state_field(N_ELEGIR_RUBRO, 'propuesta_actual', occurrence=0)!r}"),
            _log("Turno 2 (rechaza el rubro propuesto y aclara \"necesito un plomero\"): rama de \"Confirmó Rubro?\"",
                 detail=f"branch={conv.branch_taken(N_CONFIRMO_RUBRO, occurrence=0)!r}"),
            _c("Turno 2: el bot volvió a preguntar (no vacío)", bool(pide_confirmacion_2)),
            _ran_all(
                "Turno 2: volvió a elegir rubro tras el rechazo (2ª ejecución de elegir_rubro, SIN re-pegarle a /rubros)",
                conv, N_ELEGIR_RUBRO,
            ),
        ]
        rubro_1a = conv.state_field(N_ELEGIR_RUBRO, 'propuesta_actual', occurrence=0)
        rubro_2a = conv.state_field(N_ELEGIR_RUBRO, 'propuesta_actual', occurrence=1)
        checks.append(_log("Rubro ofrecido (2ª propuesta, tras la corrección del vecino)", detail=f"{rubro_2a!r}"))
        rubros_total = conv.state_field(N_BUSCAR_RUBROS, 'rubros_total', occurrence=0)
        # Informativo, NO assert (a diferencia del dedup de "noticias" en
        # _run_noticias): acá el mensaje de "rechazo" del vecino (m2) también
        # ACLARA la necesidad ("...necesito un plomero"), así que si la
        # clasificación de necesidad ya venía apuntando a "Plomero" desde el
        # turno 1, repetirlo en la 2ª propuesta es lo CORRECTO (coincide con
        # lo que el vecino pidió), no una falla de dedup — a diferencia de
        # "no, esa no es" en noticias, que no reafirma nada en particular.
        # Descubierto 2026-07-21 corriendo esta suite: un assert acá daba
        # falso rojo cuando la 1ª propuesta ya acertaba.
        checks.append(_log(
            "¿Repitió el mismo rubro en la 2ª propuesta habiendo más de 1 candidato?",
            detail=f"1ª={rubro_1a!r} 2ª={rubro_2a!r} rubros_total={rubros_total!r}",
        ))
        checks += [
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
            conv, N_NOTIFICAR_TRABAJADOR, N_RESPONDER_SERVICIO, N_END_CONV_OK,
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
        checks.append(_ran_all("Cerró específicamente por end_conv_scope", conv, N_END_CONV_SCOPE))
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
    `_run_servicio`), y agota los 3 `max_visits` que permite la condición
    interna de "Obtener Dirección Confirmada" (`N_VALIDAR_DIRECCION`, antes
    "Tienen dirección?"/`validar_direccion` como nodos sueltos, confirmado en
    vivo 2026-07-12, migrado a nodo_flow "get_data" el 2026-07-20) sin dar
    nunca una dirección real — el flow debe cerrar solo igual, por la rama de
    disculpa (`not_found` → disculpar_dir → end_conv_fail), no quedarse
    colgado. Un camino infeliz también tiene que TERMINAR.

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
            conv, N_END_CONV_FAIL,
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
        id="comercio", title="Comercio — aclaración + resiliencia a ambiguo + ferretería + confirmación",
        desc="Arranca con un saludo ambiguo (pide aclaración), tolera un mensaje sin sentido en el medio sin romperse, "
             "se resuelve al dar el pedido real — fetch real del directorio de comercios — y recién cierra tras "
             "rechazar una propuesta y confirmar la segunda (patrón confirm_choice, igual que noticias).",
        run=_run_comercio,
    ),
    Scenario(
        id="comercio-agotado", title="[Único camino infeliz de comercio] Rechaza las 3 propuestas seguidas",
        desc="El vecino rechaza TODOS los comercios que se le proponen (3 intentos, max_visits) sin confirmar "
             "ninguno — el flow debe cerrar solo igual, por la rama de disculpa, en vez de quedar colgado.",
        run=_run_comercio_agotado,
    ),
    Scenario(
        id="comercio-sin-rubro", title="Comercio sin rubro explícito — \"Kiosco Don Jorge\" (necesidad en 1 turno)",
        desc="Un nombre propio de comercio sin decir el rubro debe resolverse en el PRIMER turno, sin pedir aclaración "
             "(regresión 2026-07-08) — y aun así cerrar de punta a punta, confirmando la propuesta (confirm_choice).",
        run=_run_comercio_sin_rubro,
    ),
    Scenario(
        id="producto", title="Producto — focos LED (necesidad directa en el saludo + rechazo + confirmación)",
        desc="Pedido de un producto puntual (focos LED) directo en el primer mensaje, sin loop de aclaración "
             "(eso ya lo cubre el escenario \"comercio\") → fetch real del directorio de productos (3 candidatos "
             "reales de QA) → propone uno, el vecino lo RECHAZA → propone otro distinto (sin repetir) → CONFIRMA → "
             "cierre.",
        run=_run_producto,
    ),
    Scenario(
        id="producto-agotado", title="[Único camino infeliz de producto] Rechaza las 3 propuestas seguidas",
        desc="El vecino rechaza TODOS los productos que se le proponen (3 intentos, max_visits) sin confirmar "
             "ninguno — el flow debe cerrar solo igual, por la rama de disculpa, en vez de quedar colgado.",
        run=_run_producto_agotado,
    ),
    Scenario(
        id="noticias", title="Noticias — corte de luz, itera propuesta rechazada + propuesta confirmada",
        desc="Consulta de noticias del barrio directo en el primer mensaje → el bot busca publicaciones reales y "
             "propone UNA con su link → el vecino la RECHAZA → el bot propone otra distinta (sin repetir, sin "
             "re-pegarle al fetch) → el vecino la CONFIRMA → cierra por la rama de éxito.",
        run=_run_noticias,
    ),
    Scenario(
        id="noticias-agotado", title="[Único camino infeliz de noticias] Rechaza las 3 propuestas seguidas",
        desc="El vecino rechaza TODAS las publicaciones que se le proponen (3 intentos, max_visits) sin confirmar "
             "ninguna — el flow debe cerrar solo igual, por la rama de disculpa con el link de Facebook como "
             "fallback, en vez de quedar colgado.",
        run=_run_noticias_agotado,
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
