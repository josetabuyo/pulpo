"""
ConditionNode — condicional determinista que setea state.route sin usar LLM.

El engine sigue solo los edges con label == state.route (igual que RouterNode).

Config:
  rules:    list[dict] — evaluadas en orden, gana la primera que matchea:
              {"var": "necesidad", "op": "not_in", "values": ["", "UNCLEAR", "OUT_OF_SCOPE"], "then": "necesidad_identificada"}
            Operadores: equals, not_equals, in, not_in, empty, not_empty, contains
  fallback: str  — route si ninguna regla matchea
  routes:   list — valores válidos (documentación de los edges disponibles)
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


def _eval_rule(rule: dict, state: FlowState) -> bool:
    var_name = rule.get("var", "")
    if not var_name:
        return False
    value = str(state.data.get(var_name, ""))
    op = rule.get("op", "equals")

    if op == "equals":
        return value == str(rule.get("value", ""))
    if op == "not_equals":
        return value != str(rule.get("value", ""))
    if op == "in":
        return value in [str(v) for v in rule.get("values", [])]
    if op == "not_in":
        return value not in [str(v) for v in rule.get("values", [])]
    if op == "empty":
        return value == ""
    if op == "not_empty":
        return value != ""
    if op == "contains":
        return str(rule.get("value", "")) in value

    logger.warning("[ConditionNode] operador desconocido: %s", op)
    return False


class ConditionNode(BaseNode):
    label = "Condición"
    color = "#92400e"
    description = "Evalúa reglas sobre variables del estado y decide qué rama ejecutar. Sin LLM — decisión pura."

    async def run(self, state: FlowState) -> FlowState:
        rules = self.config.get("rules", [])
        fallback = self.config.get("fallback", "")

        for rule in rules:
            if _eval_rule(rule, state):
                then = rule.get("then", "")
                if then:
                    logger.info("[ConditionNode] var=%s op=%s → '%s'", rule.get("var"), rule.get("op"), then)
                    state.data["route"] = then
                    return state

        logger.info("[ConditionNode] ninguna regla matcheó → fallback '%s'", fallback)
        state.data["route"] = fallback
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "rules": {
                "type":    "json",
                "label":   "Reglas (en orden, gana la primera que matchea)",
                "default": [],
                "hint":    '[{"var": "necesidad", "op": "not_in", "values": ["", "UNCLEAR", "OUT_OF_SCOPE"], "then": "necesidad_identificada"}]'
                           ' — ops: equals, not_equals, in, not_in, empty, not_empty, contains',
            },
            "fallback": {
                "type":    "string",
                "label":   "Ruta por defecto",
                "default": "",
                "hint":    "Si ninguna regla matchea",
            },
            "routes": {
                "type":    "list",
                "label":   "Rutas válidas",
                "default": [],
                "hint":    "Separadas por coma — documentación de los edges disponibles",
            },
        }
