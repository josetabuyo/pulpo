"""
DetectConversationNode — detecta si hay una conversación abierta y rutea según su antigüedad.

Lee state.data["_has_open_conv"] y state.data["_conv_age_minutes"] (inyectados
por el dispatcher antes de ejecutar el flow).

Config:
  resume_threshold_minutes:  int  — si age < esto → ruta "resumir" (default: 30)
  new_threshold_minutes:     int  — si age > esto → ruta "nueva" (default: 1440 = 24h)
  fallback:                  str  — ruta si no hay conversación abierta (default: "nueva")

Rutas de salida: "resumir" | "preguntar" | "nueva"
  resumir:   conversación reciente → continuar automáticamente
  preguntar: conversación mediana → preguntar al usuario
  nueva:     sin conversación o muy antigua → empezar de cero
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class DetectConversationNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        has_open   = bool(state.data.get("_has_open_conv", False))
        age_min    = int(state.data.get("_conv_age_minutes", 0) or 0)
        resume_thr = int(self.config.get("resume_threshold_minutes", 30))
        new_thr    = int(self.config.get("new_threshold_minutes", 1440))
        fallback   = self.config.get("fallback", "nueva")

        if not has_open:
            route = fallback
        elif age_min < resume_thr:
            route = "resumir"
        elif age_min > new_thr:
            route = "nueva"
        else:
            route = "preguntar"

        logger.info("[detect_conv] has_open=%s age=%dmin → %s", has_open, age_min, route)
        state.data["route"] = route
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "resume_threshold_minutes": {
                "type": "number", "label": "Minutos para retomar automático",
                "default": 30, "hint": "Si la conv tiene menos de N min → resumir sin preguntar",
            },
            "new_threshold_minutes": {
                "type": "number", "label": "Minutos para considerar nueva",
                "default": 1440, "hint": "Si la conv tiene más de N min (default=24h) → nueva",
            },
            "fallback": {
                "type": "string", "label": "Ruta si no hay conv abierta",
                "default": "nueva",
            },
        }
