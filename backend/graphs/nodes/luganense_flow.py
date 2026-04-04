"""
LuganenseFlowNode — delega al grafo LangGraph de Luganense.

Config:
  image_enabled: bool  (default: True)
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class LuganenseFlowNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        image_enabled = self.config.get("image_enabled", True)
        try:
            from graphs import luganense as luganense_graph
            result = await luganense_graph.invoke(
                state.message,
                "",  # prompt extra — vacío, el grafo tiene su propio system prompt
                state.bot_name,
                state.empresa_id,
                cliente_phone=state.contact_phone,
                canal=state.canal,
                image_enabled=image_enabled,
            )
            if isinstance(result, dict):
                state.reply = result.get("reply", "")
                state.image_url = result.get("image_url", "")
            else:
                state.reply = str(result) if result else ""
        except Exception as e:
            logger.error("[LuganenseFlowNode] Error ejecutando grafo: %s", e)
        return state
