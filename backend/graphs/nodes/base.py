"""
BaseNode — contrato mínimo que todo nodo debe cumplir.
"""
import re
from .state import FlowState


def interpolate(template: str, state: FlowState) -> str:
    """
    Reemplaza placeholders {{field}} con valores de FlowState.

    Campos disponibles:
      {{message}}       — mensaje entrante del usuario
      {{reply}}         — reply acumulado hasta este nodo
      {{context}}       — contexto acumulado (fetch/search/llm)
      {{query}}         — query expandida
      {{contact_name}}  — nombre del contacto
      {{contact_phone}} — teléfono del contacto
      {{bot_name}}      — nombre del bot/empresa
      {{empresa_id}}    — id de la empresa
      {{canal}}         — whatsapp | telegram
    """
    builtin = {
        "message":       state.message or "",
        "reply":         state.reply or "",
        "context":       state.context or "",
        "query":         state.query or "",
        "contact_name":  state.contact_name or "",
        "contact_phone": state.contact_phone or "",
        "bot_name":      state.bot_name or "",
        "empresa_id":    state.empresa_id or "",
        "canal":         state.canal or "",
    }
    # state.vars tiene prioridad — valores dinámicos escritos por nodos anteriores
    all_fields = {**builtin, **{k: str(v) for k, v in state.vars.items()}}

    def replace(match):
        key = match.group(1).strip()
        return all_fields.get(key, match.group(0))  # deja {{unknown}} intacto

    return re.sub(r"\{\{(\w+)\}\}", replace, template)


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
