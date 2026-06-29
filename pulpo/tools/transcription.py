"""
Transcripción de mensajes de audio.
Intenta Groq API (whisper-large-v3) y cae a pywhispercpp local si falla.
"""
import os
import logging

logger = logging.getLogger(__name__)


async def transcribe(audio_path: str) -> str:
    try:
        return await _transcribe_groq(audio_path)
    except Exception as e:
        logger.warning("Groq falló (%s), usando fallback local", e)
        return _transcribe_local(audio_path)


async def _transcribe_groq(audio_path: str) -> str:
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY no configurada")
    client = Groq(api_key=api_key)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3", file=f, language="es"
        )
    return result.text


def _transcribe_local(audio_path: str) -> str:
    try:
        from pywhispercpp.model import Model
        model = Model("small", n_threads=4)
        segments = model.transcribe(audio_path)
        return " ".join([s.text for s in segments])
    except ImportError:
        return "[audio sin transcribir — configurar GROQ_API_KEY o instalar pywhispercpp]"
