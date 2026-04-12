"""
TranscribeAudioNode — transcribe un mensaje de audio a texto.

Lee el archivo desde state.attachment_path cuando state.message_type == "audio",
llama a tools.transcription.transcribe() y escribe el resultado en state.message.
Si no hay audio o ya hay texto en state.message, pasa sin hacer nada.

Diseño: nodo tonto — solo transcribe. No decide si procesar o no.
Colocar antes de save_attachment y summarize en el flow.
"""
import logging
import os
from pathlib import Path

from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class TranscribeAudioNode(BaseNode):

    async def run(self, state: FlowState) -> FlowState:
        if state.message_type != "audio":
            return state
        if state.message:
            # Ya hay texto (ej: transcripto por otro medio) — no hacer nada
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
