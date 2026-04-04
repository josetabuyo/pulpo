"""
BaseNode — contrato mínimo que todo nodo debe cumplir.
"""
from .state import FlowState


class BaseNode:
    def __init__(self, config: dict):
        self.config = config

    async def run(self, state: FlowState) -> FlowState:
        raise NotImplementedError(f"{self.__class__.__name__}.run() no implementado")

    @classmethod
    def config_schema(cls) -> dict:
        """
        Devuelve el schema de configuración para este tipo de nodo.

        Formato:
        {
            "campo": {
                "type": "string|url|select|bool|float",
                "label": "Texto para UI",
                "default": valor_por_defecto,
                "options": ["op1", "op2"],  # solo para type="select"
                "required": True|False,
            },
            ...
        }
        """
        return {}
