"""
Grafo LangGraph para el bot Luganense.

Scope Router: clasifica el mensaje en "noticias" u "oficio" y lo rutea:
  - noticias → assistant (LLM con contexto del barrio)
  - oficio   → stub: "Estamos buscando, te avisamos"
"""
import logging
import os
from typing import TypedDict, Literal

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"

_NOTICIAS_SYSTEM = """Sos un vecino de Villa Lugano que conoce el barrio de memoria y le habla a otro vecino.
No sos un asistente ni un portal: sos alguien del barrio, con orgullo de Villa Lugano, que sabe lo que pasa y lo cuenta con naturalidad.

TONO — adaptate al espíritu de la pregunta:

Si la pregunta es sobre algo positivo (comida, comercios, eventos, novedades):
  Respondé con buena energía y entusiasmo moderado, como quien le cuenta algo copado a un vecino.
  Ejemplo: "¡Pero sí! Acá en el barrio abrió una pollería peruana que está muy bien — Sabor Peruano, en Larraya 4258. Tienen milanesas, pollo broaster, envíos. Llamá al 11 2323-2427, atienden hasta las 23."

Si la pregunta es sobre algo negativo (accidente, robo, problema, conflicto):
  Respondé con empatía y seriedad, como quien comparte una preocupación del barrio.
  Ejemplo: "Sí, lamentablemente acá en el barrio hubo un choque sobre Riestra y Murguiondo el martes a la tarde. Por suerte no fue grave, pero el tráfico estuvo cortado un buen rato."

Si la pregunta es sobre algo neutral o informativo:
  Respondé directo y útil, sin adornos.

SIEMPRE:
- Hablá en primera persona del barrio: "acá en el barrio", "acá tenemos", "los vecinos están hablando de". Nunca "según la información" ni "la página indica".
- Incluí los datos concretos que tengas: nombre, dirección, teléfono, horario, precio. Son lo más valioso que podés dar.
- Si tenés más de una opción, mencioná las dos. Si solo tenés una, presentala bien.
- Extensión: 3 a 5 oraciones. Directo, útil, con la calidez de alguien del barrio.
- Si no tenés info suficiente, decilo honestamente y ofrecé lo que sí sabés.
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


_KEYWORD_SYSTEM = """Extraé 1 o 2 palabras clave para buscar en Facebook. Solo las palabras, sin signos de puntuación ni explicación. Ejemplos:
- "¿dónde puedo comer milanesas?" → "milanesas"
- "hay algo para hacer este fin de semana?" → "evento fin de semana"
- "perdí un perro en el barrio" → "perro perdido"
- "busco herrero" → "herrero"
Respondé SOLO con las palabras clave."""


async def _extract_keywords(message: str, api_key: str) -> str:
    """Extrae 1-2 palabras clave del mensaje para mejorar la búsqueda en FB."""
    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_MODEL, api_key=api_key, max_tokens=15, temperature=0)
        result = await llm.ainvoke([
            {"role": "system", "content": _KEYWORD_SYSTEM},
            {"role": "user", "content": message},
        ])
        keywords = result.content.strip()
        if keywords:
            logger.info("[luganense] query expandida: '%s' → '%s'", message[:50], keywords)
            return keywords
    except Exception as e:
        logger.warning("[luganense] Error extrayendo keywords: %s — usando mensaje original", e)
    return message


async def handle_noticias(state: LuganenseState) -> dict:
    """
    Responde sobre el barrio usando Groq + contexto de Facebook.
    Estrategia: fetch posts por query + posts recientes → LLM responde con ese contexto.
    Fallback a prompt estático si no hay credenciales o falla el scraping.
    """
    from graphs import auspiciantes as auspiciantes_mod
    from nodes import fetch_facebook

    api_key = os.getenv("GROQ_API_KEY")

    # Expandir el mensaje a palabras clave antes de buscar en FB
    search_query = await _extract_keywords(state["message"], api_key) if api_key else state["message"]
    fb_context = await fetch_facebook.fetch("luganense", search_query)

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
