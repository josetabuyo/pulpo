"""
ConditionNode — condicional determinista que setea state.route sin usar LLM.

El engine sigue solo los edges con label == state.route (igual que RouterNode).

Config:
  rules:    list[dict] — evaluadas en orden, gana la primera que matchea:
              {"var": "necesidad", "op": "not_in", "values": ["", "UNCLEAR", "OUT_OF_SCOPE"], "then": "necesidad_identificada"}
            Operadores: equals, not_equals, in, not_in, empty, not_empty, contains
            `var` se interpola contra el state (soporta "{{output}}") — así un
            sub-flow reusable (nodo_flow) puede parametrizar sobre qué clave
            del estado del padre decide, en vez de una var fija.
  fallback: str  — route si ninguna regla matchea
  routes:   list — valores válidos (documentación de los edges disponibles)
  max_visits: int — si el nodo se visita ≥ N veces en la misma conversación, redirige a max_visits_route
  max_visits_route: str — route a la que redirige al agotar max_visits
"""
import logging
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


def _eval_rule(rule: dict, state: FlowState) -> bool:
    var_name = interpolate(rule.get("var", ""), state)
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
        max_visits = self.config.get("max_visits")
        max_visits_route = self.config.get("max_visits_route", "")

        route = fallback
        for rule in rules:
            if _eval_rule(rule, state):
                then = rule.get("then", "")
                if then:
                    logger.info("[ConditionNode] var=%s op=%s → '%s'", rule.get("var"), rule.get("op"), then)
                    route = then
                    break
        else:
            logger.info("[ConditionNode] ninguna regla matcheó → fallback '%s'", fallback)

        # Límite de reintentos: solo cuenta/aplica cuando el resultado quedó en
        # fallback (loop sin resolver) — así un acierto justo en la última visita
        # no se pisa con max_visits_route. (Bug real: antes el chequeo corría
        # ANTES de evaluar las reglas, forzando fatiga aunque ESA visita
        # resolviera bien — ej. el 3er intento matchea una regla válida pero
        # igual se fuerza a max_visits_route solo por ser la 3ra visita.)
        if max_visits and max_visits_route and route == fallback:
            visit_key = f"_visits_{self.config.get('_node_id', 'condition')}"
            visits = int(state.data.get(visit_key, 0) or 0) + 1
            state.data[visit_key] = visits
            logger.debug("[ConditionNode] visitas=%d/%s node=%s", visits, max_visits, visit_key)
            if visits >= int(max_visits):
                logger.info("[ConditionNode] max_visits=%s alcanzado → '%s'", max_visits, max_visits_route)
                route = max_visits_route

        state.data["route"] = route
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
            "max_visits": {
                "type":    "number",
                "label":   "Máx. visitas (loop limit)",
                "default": None,
                "hint":    "Si el nodo se visita ≥ N veces en la misma conversación, redirige a max_visits_route",
            },
            "max_visits_route": {
                "type":    "string",
                "label":   "Ruta cuando se agota el límite",
                "default": "",
                "hint":    "Debe existir como edge de este nodo. Ej: agotado",
            },
        }
