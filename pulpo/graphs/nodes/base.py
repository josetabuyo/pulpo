"""
BaseNode — contrato mínimo que todo nodo debe cumplir.
"""
import json
import logging
import re
from .state import FlowState

logger = logging.getLogger(__name__)


_CONV_ORIGIN_LABELS = {"user": "Usuario", "bot_reply": "Bot"}

# {{conversation}} | {{conversation.first}} | {{conversation.last}} | {{conversation[i]}}
# con sufijo opcional .origin / .content (default: .content)
_CONVERSATION_RE = re.compile(
    r"\{\{conversation(?:\.(first|last)|\[(-?\d+)\])?(?:\.(origin|content))?\}\}"
)


def _format_conversation(entries: list[dict]) -> str:
    lines = []
    for entry in entries:
        origin = entry.get("origin", "")
        label = _CONV_ORIGIN_LABELS.get(origin, origin)
        lines.append(f"{label}: {entry.get('content', '')}")
    return "\n".join(lines)


def _replace_conversation(template: str, state: FlowState) -> str:
    entries = state.data.get("conversation") or []

    def replace(match):
        first_last, idx_str, field = match.groups()
        if first_last is None and idx_str is None:
            return _format_conversation(entries)
        idx = 0 if first_last == "first" else -1 if first_last == "last" else int(idx_str)
        try:
            entry = entries[idx]
        except IndexError:
            logger.debug("[interpolate] conversation[%s] fuera de rango", idx)
            return match.group(0)  # deja el placeholder intacto
        return str(entry.get(field or "content", ""))

    return _CONVERSATION_RE.sub(replace, template)


def _stringify(value) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        return str(value)


def interpolate(template: str, state: FlowState) -> str:
    """
    Reemplaza placeholders {{field}} con valores de FlowState.

    Conversación (turnos acumulados de esta ejecución de flow, ver state.py):
      {{conversation}}              — transcripción completa ("Usuario: ...\\nBot: ...")
      {{conversation.first}}        — contenido del primer turno
      {{conversation.last}}         — contenido del último turno
      {{conversation[i]}}           — contenido del turno en el índice i (soporta negativos)
      {{conversation.last.origin}}  — origin del turno ("user" | "bot_reply"), idem con [i]/.first

    Campos meta (siempre disponibles, prioridad sobre state.data):
      {{contact_name}}  — nombre del contacto
      {{contact_phone}} — teléfono/id del contacto
      {{bot_name}}      — nombre del bot
      {{bot_id}}        — id del bot
      {{canal}}         — whatsapp | telegram

    Cualquier clave en state.data también es un placeholder válido:
      {{reply}}, {{context}}, {{route}}, {{nombre}}, {{trabajador}}, etc.
      Listas y dicts (ej. salida de un FetchHttpNode con array_input, o de un
      LLMNode con output_as_list) se insertan serializados como JSON.
    """
    template = _replace_conversation(template, state)

    meta = {
        "contact_name":  state.contact_name or "",
        "contact_phone": state.contact_phone or "",
        "bot_name":      state.bot_name or "",
        "bot_id":        state.bot_id or "",
        "canal":         state.canal or "",
    }
    # meta tiene prioridad — no debe poder ser sombreado por una clave de negocio en data.
    # None se excluye a propósito: deja el placeholder {{key}} sin resolver en vez de
    # ocultar el fallo con un string vacío — más fácil de detectar en el prompt final.
    business_data = {k: _stringify(v) for k, v in state.data.items() if v is not None}
    all_fields = {**business_data, **meta}

    def replace(match):
        key = match.group(1).strip()
        if key not in all_fields:
            logger.debug("[interpolate] placeholder sin resolver: {{%s}}", key)
            return match.group(0)  # deja {{unknown}} intacto
        return all_fields[key]

    return re.sub(r"\{\{(\w+)\}\}", replace, template)


def is_sim(state: FlowState) -> bool:
    """True si el FlowState corresponde a una ejecución de simulación in-band
    (ver management/HANDOFF_SIMULACION_V2.md — setea `state.data["_sim"]`
    el endpoint `/api/flows/{flow_id}/simulate`)."""
    return bool(state.data.get("_sim"))


class BaseNode:
    # Metadatos de UI del nodo — leídos por graphs/node_types.py para armar el
    # catálogo que consumen el editor de flows y el CLI (`pulpo flows node-types`).
    # Toda clase registrada en NODE_REGISTRY debe sobreescribir estos tres.
    label: str = "Nodo"
    color: str = "#475569"
    description: str = ""

    # Simulación in-band (management/HANDOFF_SIMULACION_V2.md):
    #   "real"    — corre sin cambios en simulación (default).
    #   "guarded" — corre su lógica real, pero saltea el side-effect externo
    #               peligroso cuando is_sim(state) es True (ver cada nodo).
    #   "mock"    — reservado, no usado hoy.
    SIM_MODE: str = "real"

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
