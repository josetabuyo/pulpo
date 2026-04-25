"""
Grafo LangGraph para el bot Luganense.

El agente tiene 3 fuentes de información y el scope_router decide cuál usar:

  noticias    → expandir_consulta → buscar_posts_fb → responder_noticias
  oficio      → buscar_oficio → notificar_oficio
  auspiciante → buscar_auspiciante → responder_auspiciante

Fuentes:
  - Facebook (noticias): scraping de la página luganense en FB
  - Oficios: lista interna de trabajadores por oficio (config/oficios/)
  - Auspiciantes: lista interna de negocios patrocinadores (config/auspiciantes/)
"""
import asyncio
import logging
import os
from typing import TypedDict, Literal

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"

# ─── Prompts ─────────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """Sos un clasificador de mensajes para un bot de barrio.
Dado un mensaje de un vecino, clasificalo en UNA de estas tres categorías:

- noticias: el vecino pregunta sobre el barrio, eventos, novedades, accidentes, adopciones de mascotas, info general o cualquier pregunta sobre lo que pasa en la comunidad
- oficio: el vecino busca contratar a alguien para que HAGA un trabajo específico (herrero, electricista, plomero, pintor, gasista, carpintero, mecánico, albañil, techista, etc.)
- auspiciante: el vecino busca un negocio, producto o servicio local (ferretería, comida, delivery, abogado, médico, salud, materiales, etc.)

En caso de duda entre noticias y otro, elegí noticias.
Respondé SOLO con una palabra: "noticias", "oficio" o "auspiciante". Sin explicaciones."""

_QUERIES_SYSTEM = """Generá una lista de búsquedas para encontrar en Facebook el contenido que pide el vecino.
Devolvé entre 1 y 3 búsquedas, una por línea, sin numeración ni explicación.

Reglas:
- Si hay una intersección "A y B": generá tres líneas — "A y B", "A", "B"
- Si hay un nombre propio (persona, mascota, negocio, lugar): incluilo en al menos una búsqueda
- No repitas búsquedas equivalentes
- Sé específico: preferí términos que aparecerían en un post de Facebook de barrio

Ejemplos:
"¿dónde puedo comer milanesas?" → milanesas
"encontré un perro en Pola y Hubac" → Pola y Hubac / Pola / Hubac
"perro Loki" → Loki / perro perdido
"accidente en Riestra" → Riestra accidente"""

_NOTICIAS_SYSTEM = """Sos un vecino de Villa Lugano que conoce el barrio de memoria y le habla a otro vecino.
No sos un asistente ni un portal: sos alguien del barrio, con orgullo de Villa Lugano, que sabe lo que pasa y lo cuenta con naturalidad.

TONO — adaptate al espíritu de la pregunta:
- Positivo (comida, comercios, eventos): buena energía, entusiasta pero natural.
- Negativo (accidente, robo, problema): empático y serio.
- Neutral/informativo: directo y útil, sin adornos.

SIEMPRE:
- Hablá en primera persona del barrio. Nunca "según la información" ni "la página indica".
- Incluí datos concretos: nombre, dirección, teléfono, horario, precio.
- Extensión: 3 a 5 oraciones.
- Si no tenés info suficiente, decilo honestamente.

IMPORTANTE: respondé directamente con el texto para el vecino, sin JSON ni formato extra.

_AUSPICIANTE_SYSTEM = """Sos el vocero de Luganense, el portal comunitario de Villa Lugano.
Un vecino preguntó por algo y tenés información de un negocio del barrio que puede ayudarlo.

Tu tarea: escribir una respuesta natural y útil, como si le recomendaras el negocio a un vecino.
- Presentá el negocio con entusiasmo genuino, sin sonar a publicidad forzada.
- Incluí los datos de contacto del mensaje del auspiciante.
- Extensión: 2 a 4 oraciones.
- Español rioplatense natural: "vos", "che", "dale".

Mensaje del auspiciante a incluir:
{auspiciante_msg}"""


# ─── State ───────────────────────────────────────────────────────────────────

class LuganenseState(TypedDict):
    # Input
    message: str
    prompt: str
    bot_name: str
    empresa_id: str
    cliente_phone: str
    canal: str

    # Routing
    scope: str                   # "noticias" | "oficio" | "auspiciante"

    # Rama noticias
    queries: list[str]           # búsquedas generadas para FB
    fb_posts: list[dict]         # [{"text": str, "url": str}]
    fb_context: str              # texto combinado para el LLM

    # Rama oficio
    oficio: str                  # oficio identificado por el LLM
    worker: dict | None          # trabajador encontrado (o None)

    # Rama auspiciante
    auspiciante_nombre: str
    auspiciante_msg: str         # mensaje del auspiciante encontrado

    # Output
    reply: str


# ─── Nodo: scope_router ──────────────────────────────────────────────────────

async def scope_router(state: LuganenseState) -> dict:
    """Clasifica el mensaje en una de 3 fuentes: noticias | oficio | auspiciante."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("[luganense] GROQ_API_KEY no configurada")
        return {"scope": "noticias"}

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_MODEL, api_key=api_key, max_tokens=10, temperature=0)
        result = await llm.ainvoke([
            {"role": "system", "content": _ROUTER_SYSTEM},
            {"role": "user", "content": state["message"]},
        ])
        scope = result.content.strip().lower()
        if scope not in ("noticias", "oficio", "auspiciante"):
            scope = "noticias"
        logger.info("[luganense] scope_router → '%s' | msg: %s", scope, state["message"][:60])
        return {"scope": scope}
    except Exception as e:
        logger.error("[luganense] Error en scope_router: %s", e)
        return {"scope": "noticias"}


# ─── Rama noticias ────────────────────────────────────────────────────────────

async def expandir_consulta(state: LuganenseState) -> dict:
    """Genera 1-3 queries de búsqueda para Facebook a partir del mensaje."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"queries": [state["message"]]}

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_MODEL, api_key=api_key, max_tokens=40, temperature=0)
        result = await llm.ainvoke([
            {"role": "system", "content": _QUERIES_SYSTEM},
            {"role": "user", "content": state["message"]},
        ])
        lines = [l.strip() for l in result.content.strip().splitlines() if l.strip()]
        queries = lines[:3] if lines else [state["message"]]
        logger.info("[luganense] expandir_consulta → %s", queries)
        return {"queries": queries}
    except Exception as e:
        logger.warning("[luganense] Error en expandir_consulta: %s — usando mensaje original", e)
        return {"queries": [state["message"]]}


async def buscar_posts_fb(state: LuganenseState) -> dict:
    """Scrapea Facebook en paralelo para cada query. Devuelve posts con texto e imagen."""
    from nodes import fetch_facebook

    empresa_id = state.get("empresa_id", "luganense")
    queries = state.get("queries") or [state["message"]]

    results = await asyncio.gather(*[
        fetch_facebook.fetch_posts(empresa_id, q) for q in queries
    ])

    # Deduplicar por texto
    seen: set[str] = set()
    fb_posts: list[dict] = []
    for posts in results:
        for post in posts:
            key = post["text"][:100]
            if key not in seen:
                seen.add(key)
                fb_posts.append(post)

    fb_context = "\n\n".join(p["text"] for p in fb_posts if p["text"])
    logger.info(
        "[luganense] buscar_posts_fb: %d posts únicos, %d chars",
        len(fb_posts), len(fb_context),
    )
    return {"fb_posts": fb_posts, "fb_context": fb_context}


async def responder_noticias(state: LuganenseState) -> dict:
    """Genera la respuesta sobre el barrio usando el contexto de Facebook."""
    api_key = os.getenv("GROQ_API_KEY")
    fb_context = state.get("fb_context", "")

    if not api_key:
        logger.error("[luganense] GROQ_API_KEY no configurada — fallback a assistant.ask")
        from tools import assistant as assistant_mod
        context = (
            "Sos el asistente de Luganense. Respondé en base a estas publicaciones:\n\n" + fb_context
            if fb_context else state["prompt"]
        )
        reply = await assistant_mod.ask(context, state["message"], state["bot_name"]) or ""
        return {"reply": reply}

    fb_posts = state.get("fb_posts", [])
    system = _NOTICIAS_SYSTEM
    if fb_context:
        indexed = "\n\n".join(
            f"[Post {i}]\n{p['text']}"
            for i, p in enumerate(fb_posts)
            if p["text"]
        )
        system = _NOTICIAS_SYSTEM + f"\n\nPublicaciones de la página:\n\n{indexed}"

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_MODEL, api_key=api_key, temperature=0.3)
        result = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": state["message"]},
        ])
        reply = result.content or ""
        logger.info("[luganense] responder_noticias: %d chars", len(reply))
        return {"reply": reply}

    except Exception as e:
        logger.error("[luganense] Error en responder_noticias: %s — fallback", e)
        from tools import assistant as assistant_mod
        context = (
            "Sos el asistente de Luganense. Respondé en base a estas publicaciones:\n\n" + fb_context
            if fb_context else state["prompt"]
        )
        reply = await assistant_mod.ask(context, state["message"], state["bot_name"]) or ""
        return {"reply": reply}


# ─── Rama oficio ──────────────────────────────────────────────────────────────

async def buscar_oficio(state: LuganenseState) -> dict:
    """Identifica el oficio pedido y busca un trabajador disponible en la lista interna."""
    from nodes import find_worker
    oficio, worker = await find_worker.find(state["message"], state["empresa_id"])
    logger.info("[luganense] buscar_oficio: oficio='%s' worker=%s", oficio, worker["nombre"] if worker else None)
    return {"oficio": oficio, "worker": worker}


async def notificar_oficio(state: LuganenseState) -> dict:
    """Notifica al trabajador encontrado, registra el pedido y genera el reply."""
    from nodes import notify_worker
    from db import create_job

    oficio = state.get("oficio", "otro")
    worker = state.get("worker")

    if worker:
        await notify_worker.notify(worker, state["message"], state["empresa_id"])
        await create_job(
            empresa_id=state["empresa_id"],
            cliente_phone=state.get("cliente_phone", ""),
            canal=state.get("canal", "telegram"),
            oficio=oficio,
            trabajador_id=worker.get("telegram_id") or worker.get("whatsapp"),
            trabajador_nombre=worker["nombre"],
        )
        nombre = worker["nombre"]
        reply = (
            f"¡Encontramos a alguien! *{nombre}* puede ayudarte con tu pedido de {oficio} 🙌\n"
            f"Te va a contactar pronto."
        )
        if worker.get("whatsapp"):
            reply += f"\n📞 También podés contactarlo directo: {worker['whatsapp']}"
    else:
        await create_job(
            empresa_id=state["empresa_id"],
            cliente_phone=state.get("cliente_phone", ""),
            canal=state.get("canal", "telegram"),
            oficio=oficio,
        )
        oficio_display = oficio if oficio != "otro" else "profesional"
        reply = (
            f"Estamos buscando un {oficio_display} para vos 🔍\n"
            f"Te avisamos cuando tengamos novedades."
        )

    return {"reply": reply}


# ─── Rama auspiciante ─────────────────────────────────────────────────────────

async def buscar_auspiciante(state: LuganenseState) -> dict:
    """Busca el auspiciante más relevante para la consulta del vecino (match por tags)."""
    from graphs import auspiciantes as auspiciantes_mod
    nombre, mensaje = auspiciantes_mod.get_relevant(state["empresa_id"], state["message"])

    if nombre:
        logger.info("[luganense] buscar_auspiciante: match → %s", nombre)
    else:
        logger.info("[luganense] buscar_auspiciante: sin match por tags")

    return {
        "auspiciante_nombre": nombre or "",
        "auspiciante_msg": mensaje or "",
    }


async def responder_auspiciante(state: LuganenseState) -> dict:
    """Genera una respuesta natural que presenta el auspiciante al vecino."""
    auspiciante_msg = state.get("auspiciante_msg", "")

    if not auspiciante_msg:
        # Sin match → respuesta genérica
        reply = (
            "Hmm, en este momento no tengo un negocio del barrio para eso, "
            "pero podés consultar en la página de Luganense para más info. 🙌"
        )
        return {"reply": reply}

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"reply": auspiciante_msg}

    try:
        from langchain_groq import ChatGroq
        system = _AUSPICIANTE_SYSTEM.format(auspiciante_msg=auspiciante_msg)
        llm = ChatGroq(model=_MODEL, api_key=api_key, temperature=0.4)
        result = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": state["message"]},
        ])
        reply = result.content or auspiciante_msg
        logger.info("[luganense] responder_auspiciante: %d chars", len(reply))
        return {"reply": reply}
    except Exception as e:
        logger.error("[luganense] Error en responder_auspiciante: %s — fallback al mensaje directo", e)
        return {"reply": auspiciante_msg}


# ─── Routing ──────────────────────────────────────────────────────────────────

def _route_scope(state: LuganenseState) -> Literal["expandir_consulta", "buscar_oficio", "buscar_auspiciante"]:
    scope = state.get("scope", "noticias")
    if scope == "oficio":
        return "buscar_oficio"
    if scope == "auspiciante":
        return "buscar_auspiciante"
    return "expandir_consulta"


# ─── Compilar el grafo ────────────────────────────────────────────────────────

_builder = StateGraph(LuganenseState)

# Nodos
_builder.add_node("scope_router",         scope_router)
_builder.add_node("expandir_consulta",    expandir_consulta)
_builder.add_node("buscar_posts_fb",      buscar_posts_fb)
_builder.add_node("responder_noticias",   responder_noticias)
_builder.add_node("buscar_oficio",        buscar_oficio)
_builder.add_node("notificar_oficio",     notificar_oficio)
_builder.add_node("buscar_auspiciante",   buscar_auspiciante)
_builder.add_node("responder_auspiciante", responder_auspiciante)

# Edges
_builder.set_entry_point("scope_router")
_builder.add_conditional_edges("scope_router", _route_scope)

# Rama noticias
_builder.add_edge("expandir_consulta",  "buscar_posts_fb")
_builder.add_edge("buscar_posts_fb",    "responder_noticias")
_builder.add_edge("responder_noticias", END)

# Rama oficio
_builder.add_edge("buscar_oficio",      "notificar_oficio")
_builder.add_edge("notificar_oficio",   END)

# Rama auspiciante
_builder.add_edge("buscar_auspiciante",    "responder_auspiciante")
_builder.add_edge("responder_auspiciante", END)

app = _builder.compile()


# ─── Punto de entrada ─────────────────────────────────────────────────────────

async def invoke(
    message: str,
    prompt: str,
    bot_name: str = "el asistente",
    empresa_id: str = "",
    cliente_phone: str = "",
    canal: str = "telegram",
) -> dict:
    """
    Invoca el grafo Luganense.
    Retorna {"reply": str}.
    """
    result = await app.ainvoke({
        "message": message,
        "prompt": prompt,
        "bot_name": bot_name,
        "empresa_id": empresa_id,
        "cliente_phone": cliente_phone,
        "canal": canal,
        "scope": "",
        "queries": [],
        "fb_posts": [],
        "fb_context": "",
        "oficio": "",
        "worker": None,
        "auspiciante_nombre": "",
        "auspiciante_msg": "",
        "reply": "",
    })
    return {"reply": result.get("reply", "")}
