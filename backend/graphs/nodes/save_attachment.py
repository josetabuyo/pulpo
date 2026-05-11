"""
SaveAttachmentNode — mueve state.attachment_path a storage permanente.

Destino: data/summaries/{empresa_id}/{contact_phone}/{filename}
(misma estructura que usa SummarizeNode)

Si no hay adjunto, pasa sin hacer nada.
Si el archivo de audio fue transcripto y ya no se necesita, se puede
configurar delete_after=true para eliminarlo tras moverlo.

Diseño: nodo tonto — solo mueve el archivo. No decide qué hacer con él.
Colocar después de transcribe_audio y antes de summarize.
"""
import logging
import shutil
from pathlib import Path

from .base import BaseNode
from .state import FlowState
from .summarize import slugify as _slugify

logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent.parent.parent.parent / "data" / "summaries"


class SaveAttachmentNode(BaseNode):

    async def run(self, state: FlowState) -> FlowState:
        if not state.attachment_path:
            return state

        src = Path(state.attachment_path)
        if not src.exists():
            return state

        empresa_id    = state.empresa_id or "unknown"
        contact_phone = state.contact_phone or state.contact_name or "unknown"
        dest_dir = _BASE / empresa_id / _slugify(contact_phone)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        try:
            shutil.move(str(src), str(dest))
            state.attachment_path = str(dest)
            logger.debug("[SaveAttachmentNode] %s → %s", src.name, dest)
        except Exception as e:
            logger.warning("[SaveAttachmentNode] No se pudo mover %s: %s", src, e)

        # Para audio: si ya fue transcripto, eliminar el archivo de audio guardado
        delete_audio = self.config.get("delete_audio_after_transcription", False)
        if delete_audio and state.message_type == "audio" and state.message:
            try:
                dest.unlink()
                state.attachment_path = None
                logger.debug("[SaveAttachmentNode] Audio eliminado tras transcripción")
            except Exception:
                pass

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "delete_audio_after_transcription": {
                "type": "bool",
                "label": "Eliminar audio tras transcribir",
                "default": False,
                "hint": "Si está activo, el archivo de audio se borra una vez transcripto.",
            },
        }
