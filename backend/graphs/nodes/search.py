"""
SearchNode — busca en fuentes internas y guarda resultado en state.context.

Config:
  search_type: str — "worker" | "auspiciante"
  empresa_id:  str — empresa (si vacío, usa state.empresa_id)
"""
import json
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class SearchNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        search_type = self.config.get("search_type", "worker")
        empresa_id  = self.config.get("empresa_id") or state.empresa_id

        if search_type == "worker":
            await self._search_worker(state, empresa_id)
        elif search_type == "auspiciante":
            self._search_auspiciante(state, empresa_id)
        else:
            logger.warning("[SearchNode] search_type desconocido: %s", search_type)

        return state

    async def _search_worker(self, state: FlowState, empresa_id: str) -> None:
        try:
            from nodes import find_worker
            oficio, worker = await find_worker.find(state.message, empresa_id)
            # Serializar resultado para que NotifyNode lo lea
            state.context = json.dumps({"oficio": oficio, "worker": worker}, ensure_ascii=False)
            logger.info("[SearchNode] worker: oficio='%s' worker=%s",
                        oficio, worker["nombre"] if worker else None)
        except Exception as e:
            logger.error("[SearchNode] Error buscando worker: %s", e)
            state.context = json.dumps({"oficio": "otro", "worker": None})

    def _search_auspiciante(self, state: FlowState, empresa_id: str) -> None:
        try:
            from graphs import auspiciantes as auspiciantes_mod
            nombre, mensaje = auspiciantes_mod.get_relevant(empresa_id, state.message)
            if mensaje:
                state.context = mensaje
                logger.info("[SearchNode] auspiciante: match '%s'", nombre)
            else:
                state.context = ""
                logger.info("[SearchNode] auspiciante: sin match")
        except Exception as e:
            logger.error("[SearchNode] Error buscando auspiciante: %s", e)
            state.context = ""

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "search_type": {"type": "select", "label": "Tipo de búsqueda", "default": "worker",
                            "options": ["worker", "auspiciante"]},
            "empresa_id":  {"type": "string", "label": "Empresa ID",       "default": ""},
        }
