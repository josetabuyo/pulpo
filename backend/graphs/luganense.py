"""
Grafo LangGraph para el bot Luganense.

Scope Router: clasifica el mensaje en "noticias" u "oficio" y lo rutea:
  - noticias → assistant (LLM con contexto del barrio)
  - oficio   → stub: "Estamos buscando, te avisamos"
"""
import asyncio
import logging
import os
from typing import TypedDict, Literal

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"

_NOTICIAS_SYSTEM = """Sos el vocero oficial de Luganense, el portal comunitario de Villa Lugano (Buenos Aires).
Tu personalidad: sos un presentador nato — cálido, porteño, con la energía de alguien que genuinamente ama el barrio y quiere que cada vecino encuentre exactamente lo que busca. Sabés leer el espíritu de cada pregunta y responder en el mismo tono: si alguien llega con hambre urgente, lo mandás directo al plato; si viene curioso, le contás como si le mostraras algo que descubriste vos mismo; si viene preocupado, lo tranquilizás y le dás la solución.

Reglas de oro:
- Leé el tono de la pregunta y respondé en ese mismo registro: informal si la pregunta es informal, urgente si hay urgencia, entusiasta si hay entusiasmo.
- Siempre terminá en un lugar positivo y con acción concreta: que el vecino salga con ganas de hacer algo con lo que le contaste.
- Presentá la información como una recomendación de alguien que conoce el barrio de memoria, no como un informe. Mencioná nombres, direcciones y detalles concretos cuando los tengas — eso es lo que hace la diferencia.
- Sé breve e impactante. Nada de ensayos. Una o dos frases con gancho valen más que cinco genéricas.
- Usá el español rioplatense natural: vos, che, dale, genial — pero sin exagerar. Que suene real, no forzado.
- NUNCA empieces con "Según la información...", "De acuerdo a...", "La página indica..." ni nada por el estilo. Hablá como Luganense, con seguridad y en primera persona del barrio: "Tenés que ir a...", "Abrió justo en...", "El barrio está hablando de...". Vos sos la fuente, no un intermediario.
- Si no tenés información suficiente, decilo con onda y ofrecé lo que sí sabés.

Ejemplo del tono buscado (pregunta: "¿dónde como milanesas?"):
MAL: "Según la información disponible, existe un restaurante que ofrece milanesas."
BIEN: "¡Che, tenés que ir a Sabor Peruano en Larraya 4258! Abrieron hace poco y ya están con todo: milanesas, pollo broaster, lomo saltado... el barrio los está descubriendo. Pedís al 11 2323-2427 o pasás de 11 a 23. ¡Dale!"
"""

_ROUTER_SYSTEM = """Sos un clasificador de mensajes para un bot de barrio.
Dado un mensaje de un vecino, clasificalo en UNA de estas dos categorías:
- noticias: el vecino pregunta sobre el barrio, noticias, eventos, actividades, novedades, adopciones de mascotas, info general, preguntas sobre la comunidad
- oficio: el vecino busca contratar un servicio o trabajador con oficio específico (herrero, electricista, plomero, pintor, gasista, carpintero, mecánico, albanil, etc.)

En caso de duda, clasificar como "noticias".
Respondé SOLO con una palabra: "noticias" o "oficio". Sin explicaciones."""


class LuganenseState(TypedDict):
    message: str
    prompt: str
    bot_name: str
    empresa_id: str
    cliente_phone: str
    canal: str
    scope: str
    reply: str


async def scope_router(state: LuganenseState) -> dict:
    """Clasifica el mensaje con Groq: 'noticias' u 'oficio'."""
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
        if scope not in ("noticias", "oficio"):
            scope = "noticias"
        logger.info("[luganense] scope_router → '%s' para: %s", scope, state["message"][:60])
        return {"scope": scope}
    except Exception as e:
        logger.error("[luganense] Error en scope_router: %s", e)
        return {"scope": "noticias"}


def _route(state: LuganenseState) -> Literal["handle_noticias", "handle_oficio"]:
    return "handle_noticias" if state["scope"] == "noticias" else "handle_oficio"


_QUERIES_SYSTEM = """Generá una lista de búsquedas para encontrar en Facebook el contenido que pide el vecino.
Devolvé entre 1 y 3 búsquedas, una por línea, sin numeración ni explicación.

Reglas:
- Si hay una intersección "A y B": generá tres líneas — "A y B", "A", "B"
- Si hay un nombre propio (persona, mascota, negocio, lugar): incluilo en al menos una búsqueda
- No repitas búsquedas equivalentes
- Sé específico: preferí términos que aparecerían en un post de Facebook de barrio

Ejemplos:
"¿dónde puedo comer milanesas?" →
milanesas
pollería

"encontré un perro en Pola y Hubac" →
Pola y Hubac
Pola
Hubac

"perro Loki" →
Loki
perro perdido

"accidente en Riestra" →
Riestra accidente

"abrió Sabor Peruano?" →
Sabor Peruano"""


async def _expand_queries(message: str, api_key: str) -> list[str]:
    """Genera 1-3 queries de búsqueda para FB a partir del mensaje del usuario."""
    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_MODEL, api_key=api_key, max_tokens=40, temperature=0)
        result = await llm.ainvoke([
            {"role": "system", "content": _QUERIES_SYSTEM},
            {"role": "user", "content": message},
        ])
        lines = [l.strip() for l in result.content.strip().splitlines() if l.strip()]
        if lines:
            logger.info("[luganense] queries generadas: %s", lines)
            return lines[:3]
    except Exception as e:
        logger.warning("[luganense] Error generando queries: %s — usando mensaje original", e)
    return [message]


async def handle_noticias(state: LuganenseState) -> dict:
    """
    Responde sobre el barrio usando Groq + contexto de Facebook.
    Estrategia: fetch posts por query + posts recientes → LLM responde con ese contexto.
    Fallback a prompt estático si no hay credenciales o falla el scraping.
    """
    from graphs import auspiciantes as auspiciantes_mod
    from nodes import fetch_facebook

    api_key = os.getenv("GROQ_API_KEY")

    # Generar múltiples queries y correrlas en paralelo
    queries = await _expand_queries(state["message"], api_key) if api_key else [state["message"]]
    results = await asyncio.gather(*[fetch_facebook.fetch("luganense", q) for q in queries])

    # Combinar resultados deduplicando líneas repetidas
    seen: set[str] = set()
    combined: list[str] = []
    for block in results:
        for line in block.splitlines():
            if line not in seen:
                seen.add(line)
                combined.append(line)
    fb_context = "\n".join(combined)
    logger.info("[luganense] contexto FB: %d chars de %d queries", len(fb_context), len(queries))

    if not api_key:
        logger.error("[luganense] GROQ_API_KEY no configurada — fallback a prompt estático")
        from tools import assistant as assistant_mod
        context = (
            "Sos el asistente de Luganense. Respondé en base a estas publicaciones:\n\n" + fb_context
            if fb_context else state["prompt"]
        )
        reply = await assistant_mod.ask(context, state["message"], state["bot_name"])
        reply = reply or ""
    else:
        try:
            from langchain_groq import ChatGroq

            system = _NOTICIAS_SYSTEM
            if fb_context:
                system = (
                    _NOTICIAS_SYSTEM
                    + "\n\nPublicaciones recientes de la página:\n\n"
                    + fb_context
                )

            llm = ChatGroq(model=_MODEL, api_key=api_key, temperature=0.3)
            result = await llm.ainvoke([
                {"role": "system", "content": system},
                {"role": "user", "content": state["message"]},
            ])
            reply = result.content or ""
            logger.info("[luganense] handle_noticias: respuesta generada (%d chars)", len(reply))

        except Exception as e:
            logger.error("[luganense] Error en Groq: %s — fallback a assistant.ask", e)
            from tools import assistant as assistant_mod
            context = (
                "Sos el asistente de Luganense. Respondé en base a estas publicaciones:\n\n" + fb_context
                if fb_context else state["prompt"]
            )
            reply = await assistant_mod.ask(context, state["message"], state["bot_name"])
            reply = reply or ""

    sponsor_msg = auspiciantes_mod.get_random(state.get("empresa_id", ""))
    if sponsor_msg:
        reply = f"{reply}\n\n---\n{sponsor_msg}"

    return {"reply": reply}


async def handle_oficio(state: LuganenseState) -> dict:
    """Identifica el oficio, busca un trabajador y notifica."""
    from nodes import find_worker, notify_worker
    from db import create_job

    oficio, worker = await find_worker.find(state["message"], state["empresa_id"])

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
        contacto = worker.get("whatsapp") or worker.get("telegram_id") or ""
        reply = (
            f"¡Encontramos a alguien! *{nombre}* puede ayudarte con tu pedido de {oficio} 🙌\n"
            f"Te va a contactar pronto."
        )
        if contacto and worker.get("whatsapp"):
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


# ─── Compilar el grafo ────────────────────────────────────────────

_builder = StateGraph(LuganenseState)
_builder.add_node("scope_router", scope_router)
_builder.add_node("handle_noticias", handle_noticias)
_builder.add_node("handle_oficio", handle_oficio)
_builder.set_entry_point("scope_router")
_builder.add_conditional_edges("scope_router", _route)
_builder.add_edge("handle_noticias", END)
_builder.add_edge("handle_oficio", END)

app = _builder.compile()


async def invoke(
    message: str,
    prompt: str,
    bot_name: str = "el asistente",
    empresa_id: str = "",
    cliente_phone: str = "",
    canal: str = "telegram",
) -> str:
    """Punto de entrada principal para invocar el grafo."""
    result = await app.ainvoke({
        "message": message,
        "prompt": prompt,
        "bot_name": bot_name,
        "empresa_id": empresa_id,
        "cliente_phone": cliente_phone,
        "canal": canal,
        "scope": "",
        "reply": "",
    })
    return result.get("reply", "")
