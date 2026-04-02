"""
Grafo LangGraph para el bot Luganense.

Flujo completo:
  Inicio
    → scope_router      (clasifica: noticias / oficio)
      → expand_queries  (LLM genera 1-3 búsquedas para FB)
        → fetch_fb      (scrapea FB en paralelo, guarda posts con texto + imagen)
          → generate_reply  (LLM genera reply + decide si necesita imagen)
            → fetch_image   (descarga imagen del post relevante, si aplica)
              → Fin
      → handle_oficio   → Fin

image_enabled: toggle por empresa en phones.json → flow_config.image_enabled
               Default True. Cuando False, fetch_image se saltea siempre.
"""
import asyncio
import json
import logging
import os
from typing import TypedDict, Literal

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"

# ─── Prompts ─────────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """Sos un clasificador de mensajes para un bot de barrio.
Dado un mensaje de un vecino, clasificalo en UNA de estas dos categorías:
- noticias: el vecino pregunta sobre el barrio, noticias, eventos, actividades, novedades, adopciones de mascotas, info general, preguntas sobre la comunidad
- oficio: el vecino busca contratar un servicio o trabajador con oficio específico (herrero, electricista, plomero, pintor, gasista, carpintero, mecánico, albanil, etc.)

En caso de duda, clasificar como "noticias".
Respondé SOLO con una palabra: "noticias" o "oficio". Sin explicaciones."""

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

IMPORTANTE — Respondé con un JSON con esta estructura exacta (sin texto fuera del JSON):
{
  "reply": "<tu respuesta al vecino>",
  "needs_image": <true o false>,
  "source_post_index": <índice 0-based del post que más usaste, o -1 si no usaste ninguno específico>
}

needs_image debe ser true SOLO si:
- El post trata sobre una mascota (perro/gato) perdida o encontrada, y hay una foto que ayudaría a identificarla
- El post tiene una foto de un negocio nuevo o evento visual cuya imagen suma valor real a la respuesta
- El vecino está preguntando específicamente por ver cómo es algo visual
En cualquier otro caso, needs_image = false."""


# ─── State ───────────────────────────────────────────────────────────────────

class LuganenseState(TypedDict):
    # Input
    message: str
    prompt: str
    bot_name: str
    empresa_id: str
    cliente_phone: str
    canal: str
    image_enabled: bool        # toggle desde phones.json → flow_config.image_enabled

    # Routing
    scope: str                 # "noticias" | "oficio"

    # Query expansion
    queries: list[str]         # búsquedas generadas para FB

    # Facebook context
    fb_posts: list[dict]       # [{"text": str, "image_url": str}]
    fb_context: str            # texto combinado para el LLM

    # Reply generation
    reply: str
    needs_image: bool          # el LLM decide si la imagen es relevante
    source_post_index: int     # índice en fb_posts del post usado (-1 = ninguno específico)

    # Image
    image_url: str             # URL final a enviar (vacío si no aplica)


# ─── Nodos ───────────────────────────────────────────────────────────────────

async def scope_router(state: LuganenseState) -> dict:
    """Clasifica el mensaje: 'noticias' u 'oficio'."""
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


async def expand_queries(state: LuganenseState) -> dict:
    """Genera 1-3 búsquedas de FB a partir del mensaje del usuario."""
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
        logger.info("[luganense] expand_queries → %s", queries)
        return {"queries": queries}
    except Exception as e:
        logger.warning("[luganense] Error en expand_queries: %s — usando mensaje original", e)
        return {"queries": [state["message"]]}


async def fetch_fb(state: LuganenseState) -> dict:
    """Scrapea FB en paralelo para cada query. Combina y deduplica posts."""
    from nodes import fetch_facebook

    empresa_id = state.get("empresa_id", "luganense")
    queries = state.get("queries") or [state["message"]]

    results = await asyncio.gather(*[
        fetch_facebook.fetch_posts(empresa_id, q) for q in queries
    ])

    # Deduplicar por texto (mismo texto = mismo post vía queries distintas)
    seen_texts: set[str] = set()
    fb_posts: list[dict] = []
    for posts in results:
        for post in posts:
            key = post["text"][:100]
            if key not in seen_texts:
                seen_texts.add(key)
                fb_posts.append(post)

    fb_context = "\n\n".join(p["text"] for p in fb_posts if p["text"])
    logger.info(
        "[luganense] fetch_fb: %d posts únicos, %d chars de contexto",
        len(fb_posts), len(fb_context),
    )
    return {"fb_posts": fb_posts, "fb_context": fb_context}


async def generate_reply(state: LuganenseState) -> dict:
    """
    LLM genera la respuesta al vecino.
    Retorna reply (str), needs_image (bool) y source_post_index (int).
    Usa JSON structured output de Groq.
    """
    from graphs import auspiciantes as auspiciantes_mod

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
        reply = _add_sponsor(reply, auspiciantes_mod, state)
        return {"reply": reply, "needs_image": False, "source_post_index": -1}

    system = _NOTICIAS_SYSTEM
    if fb_context:
        # Numeramos los posts para que el LLM pueda referenciarlos por índice
        indexed = "\n\n".join(
            f"[Post {i}]\n{p['text']}"
            for i, p in enumerate(state.get("fb_posts", []))
            if p["text"]
        )
        system = _NOTICIAS_SYSTEM + f"\n\nPublicaciones de la página (usá los índices para source_post_index):\n\n{indexed}"

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model=_MODEL,
            api_key=api_key,
            temperature=0.3,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        result = await llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": state["message"]},
        ])
        data = json.loads(result.content)
        reply = data.get("reply", "")
        needs_image = bool(data.get("needs_image", False))
        source_post_index = int(data.get("source_post_index", -1))
        logger.info(
            "[luganense] generate_reply: %d chars, needs_image=%s, post_index=%d",
            len(reply), needs_image, source_post_index,
        )
    except Exception as e:
        logger.error("[luganense] Error en generate_reply: %s — fallback a assistant.ask", e)
        from tools import assistant as assistant_mod
        context = (
            "Sos el asistente de Luganense. Respondé en base a estas publicaciones:\n\n" + fb_context
            if fb_context else state["prompt"]
        )
        reply = await assistant_mod.ask(context, state["message"], state["bot_name"]) or ""
        needs_image = False
        source_post_index = -1

    reply = _add_sponsor(reply, auspiciantes_mod, state)
    return {"reply": reply, "needs_image": needs_image, "source_post_index": source_post_index}


async def fetch_image(state: LuganenseState) -> dict:
    """
    Resuelve la imagen del post indicado por source_post_index.
    Solo llega aquí si needs_image=True e image_enabled=True (routing condicional).
    No descarga nada — la URL la usa telegram_bot para enviar la foto.
    """
    fb_posts = state.get("fb_posts", [])
    idx = state.get("source_post_index", -1)

    # Intentar el post indicado primero; si no tiene imagen, buscar el primero con imagen
    candidate = ""
    if 0 <= idx < len(fb_posts):
        candidate = fb_posts[idx].get("image_url", "")

    if not candidate:
        for post in fb_posts:
            if post.get("image_url"):
                candidate = post["image_url"]
                break

    if candidate:
        logger.info("[luganense] fetch_image: imagen lista para enviar (%s...)", candidate[:60])
    else:
        logger.info("[luganense] fetch_image: no hay imagen disponible en los posts")

    return {"image_url": candidate}


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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _add_sponsor(reply: str, auspiciantes_mod, state: LuganenseState) -> str:
    sponsor_msg = auspiciantes_mod.get_random(state.get("empresa_id", ""))
    if sponsor_msg:
        return f"{reply}\n\n---\n{sponsor_msg}"
    return reply


# ─── Routing ──────────────────────────────────────────────────────────────────

def _route_scope(state: LuganenseState) -> Literal["expand_queries", "handle_oficio"]:
    return "expand_queries" if state["scope"] == "noticias" else "handle_oficio"


def _route_image(state: LuganenseState) -> Literal["fetch_image", "__end__"]:
    """Ir a fetch_image solo si el LLM lo pidió, está habilitado, y hay imagen disponible."""
    if not state.get("needs_image"):
        return "__end__"
    if not state.get("image_enabled", True):
        return "__end__"
    has_image = any(p.get("image_url") for p in state.get("fb_posts", []))
    return "fetch_image" if has_image else "__end__"


# ─── Compilar el grafo ────────────────────────────────────────────────────────

_builder = StateGraph(LuganenseState)
_builder.add_node("scope_router",   scope_router)
_builder.add_node("expand_queries", expand_queries)
_builder.add_node("fetch_fb",       fetch_fb)
_builder.add_node("generate_reply", generate_reply)
_builder.add_node("fetch_image",    fetch_image)
_builder.add_node("handle_oficio",  handle_oficio)

_builder.set_entry_point("scope_router")
_builder.add_conditional_edges("scope_router", _route_scope)
_builder.add_edge("expand_queries", "fetch_fb")
_builder.add_edge("fetch_fb",       "generate_reply")
_builder.add_conditional_edges("generate_reply", _route_image)
_builder.add_edge("fetch_image",    END)
_builder.add_edge("handle_oficio",  END)

app = _builder.compile()


# ─── Punto de entrada ─────────────────────────────────────────────────────────

async def invoke(
    message: str,
    prompt: str,
    bot_name: str = "el asistente",
    empresa_id: str = "",
    cliente_phone: str = "",
    canal: str = "telegram",
    image_enabled: bool = True,
) -> dict:
    """
    Invoca el grafo Luganense.
    Retorna {"reply": str, "image_url": str}.
    image_url es vacío si no aplica o image_enabled=False.
    """
    result = await app.ainvoke({
        "message": message,
        "prompt": prompt,
        "bot_name": bot_name,
        "empresa_id": empresa_id,
        "cliente_phone": cliente_phone,
        "canal": canal,
        "image_enabled": image_enabled,
        "scope": "",
        "queries": [],
        "fb_posts": [],
        "fb_context": "",
        "reply": "",
        "needs_image": False,
        "source_post_index": -1,
        "image_url": "",
    })
    return {
        "reply": result.get("reply", ""),
        "image_url": result.get("image_url", ""),
    }
