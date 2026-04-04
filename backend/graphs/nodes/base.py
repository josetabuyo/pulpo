"""
BaseNode — contrato mínimo que todo nodo debe cumplir.
"""
from .state import FlowState


class BaseNode:
    def __init__(self, config: dict):
        self.config = config

    async def run(self, state: FlowState) -> FlowState:
        raise NotImplementedError(f"{self.__class__.__name__}.run() no implementado")
