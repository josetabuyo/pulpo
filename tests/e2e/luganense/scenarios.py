"""
Fuente única de las conversaciones e2e del bot Luganense — usada tanto por
`test_orquestador_vendedor_sim.py` (pytest) como por
`scripts/generate_e2e_report.py` (reporte HTML). Un solo lugar, sin duplicar
lógica entre el test y el reporte.

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
el 2026-07-10 — si el flow se edita y estos ids cambian, hay que actualizar
acá):
  node_1783192985521  telegram_trigger  "Llega Mensaje a Luganense"
  node_1783192800831  llm               "Obtener necesidad" → state.necesidad
  node_1783356000392  condition         "Condición" → necesidad_identificada | pedir_mas_info | fuera_de_scope
  node_1783192962168  router            "Elegir Mostrador" → servicio | comercio | producto | noticias
  buscar_directorio   fetch_http        "Buscar directorio (all)"
  pedir_direccion     send_message      "¿En qué dirección necesitás el servicio?"
  wait_dir            wait_user
  validar_direccion   router            "validar_direccion" → tiene_direccion | sin_direccion | agotado (max_visits=3)
  set_direccion       set_state         → state.direccion (bug real 2026-07-10: usaba {{message}}, roto — fix: {{conversation.last}})
  notificar_trabajador send_message     envío real al prestador (guarded en sim)
  disculpar_dir        llm              rama agotado
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
DIRECTORIO_API = "https://luganense.vercel.app/api/directorio/buscar"
CIERRE = "escribime cuando quieras"
TIPOS_CONTACTO_VALIDOS = {
    "telegram", "whatsapp", "instagram", "facebook", "tiktok", "twitter", "email", "telefono",
}

# ─── Node ids (ver docstring) ────────────────────────────────────────────────
N_OBTENER_NECESIDAD = "node_1783192800831"
N_CONDICION = "node_1783356000392"
N_ELEGIR_MOSTRADOR = "node_1783192962168"
N_VALIDAR_DIRECCION = "validar_direccion"
N_BUSCAR_DIRECTORIO = "buscar_directorio"
N_NOTIFICAR_TRABAJADOR = "notificar_trabajador"
N_SET_DIRECCION = "set_direccion"


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


# ─── 5. Servicio con notificación — el camino más largo: aclaración + 2 vueltas de wait_user ─

async def _run_servicio() -> ScenarioResult:
    turns = []
    async with SimConversation(BOT_ID) as conv:
        r1 = await conv.send_and_wait("hola")
        turns.append(("user", "hola")); turns.append(("bot", r1))

        m2 = "se me rompió una canilla, necesito un plomero urgente"
        pide_direccion = await conv.send_and_wait(m2)
        turns.append(("user", m2)); turns.append(("bot", pide_direccion))

        m3 = "no sé, por qué preguntás?"
        repregunta = await conv.send_and_wait(m3)
        turns.append(("user", m3)); turns.append(("bot", repregunta))

        m4 = "Av. Roca 1234, Villa Lugano"
        reply = await conv.send_and_wait(m4)
        turns.append(("user", m4)); turns.append(("bot", reply))

        checks = [
            _c("Turno 1: pidió aclaración ante el saludo ambiguo",
               conv.branch_taken(N_CONDICION, occurrence=0) == "pedir_mas_info"),
            _c("Turno 2: identificó la necesidad y clasificó la rama como \"servicio\"",
               conv.branch_taken(N_ELEGIR_MOSTRADOR) == "servicio"),
            _c("Turno 2: pidió la dirección", bool(pide_direccion) and "dirección" in pide_direccion.lower()),
            _c("Turno 3 (dirección ambigua \"no sé, por qué preguntás?\"): clasificó sin_direccion y repreguntó "
               "(1ª vuelta del loop de wait_user) en vez de avanzar",
               conv.branch_taken(N_VALIDAR_DIRECCION, occurrence=0) == "sin_direccion"),
            _c("Turno 3: repreguntó por la dirección (no dio por perdido el intento)",
               bool(repregunta) and "dirección" in repregunta.lower()),
        ]
        checks += _cierre_checks(conv, reply)
        checks.append(_c(
            "Turno 4 (dirección válida): validar_direccion clasificó tiene_direccion (2ª vuelta del loop, resuelta)",
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
        checks.append(_c(
            "La respuesta final confirma el pedido y da el contacto del prestador",
            any(kw in lower for kw in ("registrad", "avisamos", "prestador", "roberto", "gómez")),
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
    Único escenario "infeliz" de la suite: agota los 3 reintentos que permite
    `validar_direccion` (`max_visits: 3` en su config, confirmado en vivo
    2026-07-10) sin dar nunca una dirección real, y el flow debe cerrar solo
    igual — por la rama de disculpa (`agotado` → disculpar_dir → end_conv_fail),
    no quedarse colgado. Un camino infeliz también tiene que TERMINAR.
    """
    turns = []
    async with SimConversation(BOT_ID) as conv:
        m1 = "se me rompió una canilla, necesito un plomero urgente"
        r1 = await conv.send_and_wait(m1)
        turns.append(("user", m1)); turns.append(("bot", r1))

        ambiguas = ["no sé, por qué preguntás?", "no tengo idea", "ni idea che"]
        last_reply = r1
        for msg in ambiguas:
            last_reply = await conv.send_and_wait(msg)
            turns.append(("user", msg)); turns.append(("bot", last_reply))

        checks = [
            _c("Clasificó la rama como \"servicio\" y pidió dirección", bool(r1) and "dirección" in (r1 or "").lower()),
            _c(
                "Tras 3 respuestas ambiguas seguidas, validar_direccion agotó los reintentos "
                "(max_visits=3) y tomó la rama \"agotado\" en vez de repreguntar para siempre",
                conv.branch_taken(N_VALIDAR_DIRECCION) == "agotado",
                detail=f"branch={conv.branch_taken(N_VALIDAR_DIRECCION)!r} visits={conv.state_field(N_VALIDAR_DIRECCION, '_visits_validar_direccion')!r}",
            ),
            _c("El contador de reintentos (_visits_validar_direccion) llegó exactamente a 3",
               conv.state_field(N_VALIDAR_DIRECCION, "_visits_validar_direccion") == 3),
            _c("Corrió el nodo de disculpa (disculpar_dir)", conv.ran_node("disculpar_dir")),
        ]
        checks += _cierre_checks(conv, last_reply)
        lower = (last_reply or "").lower()
        checks.append(_c(
            "La disculpa igual le da al vecino el contacto del prestador para que arregle directo",
            any(kw in lower for kw in ("roberto", "gómez", "prestador", "contact")),
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
        id="servicio", title="Servicio con notificación — el camino más largo (aclaración + 2 vueltas de wait_user)",
        desc="Saludo ambiguo → aclaración → pedido de plomero → pide dirección → dirección ambigua (repregunta, "
             "1ª vuelta) → dirección válida (2ª vuelta, resuelve) → notifica al prestador real → cierra.",
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
        desc="El vecino nunca da una dirección real (3 intentos ambiguos seguidos) — validar_direccion agota sus "
             "reintentos (max_visits=3) y el flow cierra igual por la rama de disculpa, en vez de quedar colgado.",
        run=_run_servicio_agotado,
    ),
    Scenario(
        id="conectividad-telegram", title="Conectividad — Telegram real (@luganense_bot)",
        desc="Único caso de esta suite que sale por Telegram de verdad — smoke test de conectividad, no de lógica de negocio.",
        run=_run_conectividad_telegram,
        real_telegram=True,
    ),
]
