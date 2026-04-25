"""
TranscribeAudioNode — transcribe un mensaje de audio a texto.

Lee el archivo desde state.attachment_path cuando state.message_type == "audio",
llama a tools.transcription.transcribe() y escribe el resultado en state.message.
Si no hay audio o ya hay texto real en state.message, pasa sin hacer nada.
Si state.message es un placeholder conocido (blob no disponible, error, etc.)
se considera "sin transcripción" y se intenta de todas formas.

Diseño: nodo tonto — solo transcribe. No decide si procesar o no.
Colocar antes de save_attachment y summarize en el flow.
"""
import logging
import os
from pathlib import Path

from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)

# Mensajes que indican que el audio NO fue transcripto todavía.
# Si state.message es uno de estos, TranscribeAudioNode sigue intentando.
_AUDIO_PLACEHOLDERS = frozenset({
    "[audio — no disponible]",
    "[audio — sin blob]",
    "[audio — error al transcribir]",
    "[audio — archivo no encontrado]",
})


class TranscribeAudioNode(BaseNode):

    async def run(self, state: FlowState) -> FlowState:
        if state.message_type != "audio":
            return state
        if state.message and state.message not in _AUDIO_PLACEHOLDERS:
            # Ya hay transcripción real — no sobreescribir
            return state
        if not state.attachment_path:
            return state

        audio_path = state.attachment_path
        if not Path(audio_path).exists():
            state.message = "[audio — archivo no encontrado]"
            return state

        from tools import transcription
        try:
            text = await transcription.transcribe(audio_path)
            state.message = text
            logger.info("[TranscribeAudioNode] Transcripto (%d chars): %s…", len(text), text[:60])
        except Exception as e:
            logger.warning("[TranscribeAudioNode] Error al transcribir: %s", e)
            state.message = "[audio — error al transcribir]"

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {}
