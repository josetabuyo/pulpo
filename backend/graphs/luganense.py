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

_ROUTER_SYSTEM = """Sos un clasificador de mensajes para un bot de barrio.
Dado un mensaje de un vecino, clasificalo en UNA de estas dos categorías:
- noticias: el vecino pregunta sobre el barrio, noticias, eventos, actividades, novedades, info general
- oficio: el vecino busca un servicio o trabajador (herrero, electricista, plomero, pintor, gasista, carpintero, mecánico, etc.)

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


async def handle_noticias(state: LuganenseState) -> dict:
    """
    Responde sobre el barrio usando contexto dinámico de Facebook.
    Si el scraping falla o no hay credenciales, cae al prompt estático.
    Agrega un auspiciante al final.
    """
    from graphs import auspiciantes as auspiciantes_mod
    from nodes import fetch_facebook

    # Intentar contexto dinámico desde Facebook
    fb_context = await fetch_facebook.fetch(
        page_id="luganense",
        query=state["message"],
    )

    if fb_context:
        context = (
            "Sos el asistente de Luganense, el portal comunitario de Villa Lugano. "
            "Respondé en base a estas publicaciones recientes del barrio:\n\n"
            + fb_context
        )
        logger.info("[luganense] handle_noticias: usando contexto de Facebook (%d chars)", len(fb_context))
    else:
        # Fallback: prompt estático de la tool config
        context = state["prompt"]
        logger.info("[luganense] handle_noticias: fallback a prompt estático")

    from tools import assistant as assistant_mod
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
