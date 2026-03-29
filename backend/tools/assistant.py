"""
Node: assistant — responde preguntas usando un LLM con contexto estático.
Usa Groq (Llama) como modelo por defecto. Tier gratuito, sin costo.
"""
import logging
import os

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"


async def ask(context: str, question: str, bot_name: str = "el asistente") -> str | None:
    """
    Llama a Groq (Llama) con el contexto y la pregunta.
    Retorna la respuesta, o None si falla.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("[assistant] GROQ_API_KEY no configurada")
        return None

    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=api_key)
        system = (
            f"Sos el asistente de {bot_name}. "
            "Respondé solo con la información del siguiente contexto. "
            "Si no encontrás la respuesta en el contexto, decí que no tenés esa información. "
            "Respondé en español, de forma breve y amigable.\n\n"
            f"Contexto:\n{context}"
        )
        response = await client.chat.completions.create(
            model=_MODEL,
            max_tokens=400,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("[assistant] Error llamando a Groq: %s", e)
        return None
