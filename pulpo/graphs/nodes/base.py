"""
BaseNode — contrato mínimo que todo nodo debe cumplir.
"""
import re
from .state import FlowState


def interpolate(template: str, state: FlowState) -> str:
    """
    Reemplaza placeholders {{field}} con valores de FlowState.

    Campos meta (siempre disponibles):
      {{message}}       — mensaje entrante del usuario
      {{contact_name}}  — nombre del contacto
      {{contact_phone}} — teléfono/id del contacto
      {{bot_name}}      — nombre del bot
      {{bot_id}}        — id del bot
      {{canal}}         — whatsapp | telegram

    Cualquier clave en state.data también es un placeholder válido:
      {{reply}}, {{context}}, {{route}}, {{nombre}}, {{trabajador}}, etc.
    """
    meta = {
        "message":       state.message or "",
        "contact_name":  state.contact_name or "",
        "contact_phone": state.contact_phone or "",
        "bot_name":      state.bot_name or "",
        "bot_id":        state.bot_id or "",
        "canal":         state.canal or "",
    }
    # data tiene prioridad — solo escalares (listas/dicts se dejan como {{key}} literal)
    scalar_data = {k: str(v) for k, v in state.data.items() if isinstance(v, (str, int, float, bool))}
    all_fields = {**meta, **scalar_data}

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
