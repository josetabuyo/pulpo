"""
RouterNode — clasificador LLM que setea state.route.

El engine sigue solo los edges con label == state.route.

Config:
  prompt:          str  — system prompt para el clasificador
  routes:          list — valores válidos (ej: ["noticias", "oficio", "auspiciante"])
  fallback:        str  — route por defecto si el LLM no responde algo válido
  model:           str  — modelo a usar (best:cat|strategy, ollama/*, groq/*, o legacy)

El LLM recibe el mensaje del vecino como turno de usuario. Nada de state.data
se manda de más: si el prompt necesita una variable puntual (ej. "necesidad")
o el historial de conversación, tiene que referenciarla explícita como
{{necesidad}} o {{conversation}} — interpolada en el prompt (ver interpolate()
en base.py) antes de llamar al LLM.
"""
import logging
from .base import BaseNode, interpolate
from .llm import MODEL_OPTIONS, _MAX_EMPTY_RETRIES, _build_llm, _record_llm_error, parse_model_strategy
from .state import FlowState

logger = logging.getLogger(__name__)


def _eval_pre_route_rules(rules: list[dict], state: FlowState) -> str | None:
    """
    Evalúa reglas deterministas sobre state.data antes de llamar al LLM.

    Cada regla:
      { "if_var": "servicio", "not_in": ["", "otro"], "then": "servicio" }

    Devuelve la ruta de la primera regla que matchea, o None si ninguna.
    """
    for rule in rules:
        var_name = rule.get("if_var", "")
        not_in   = rule.get("not_in", [])
        then     = rule.get("then", "")
        if not var_name or not then:
            continue
        value = str(state.data.get(var_name, ""))
        if value and value not in not_in:
            return then
    return None


class RouterNode(BaseNode):
    label = "Router"
    color = "#854d0e"
    description = "Clasifica el mensaje con LLM y decide qué rama ejecutar."

    async def run(self, state: FlowState) -> FlowState:
        prompt           = self.config.get("prompt", "")
        routes           = self.config.get("routes", [])
        fallback         = self.config.get("fallback", routes[0] if routes else "")
        raw_model        = self.config.get("model", "best:instruction|local-first")
        pre_route_rules  = self.config.get("pre_route_rules", [])
        max_visits       = self.config.get("max_visits")
        max_visits_route = self.config.get("max_visits_route", "")
        model, router_strategy = parse_model_strategy(raw_model)

        # Contador automático de visitas por nodo en esta conversación
        if max_visits and max_visits_route:
            visit_key = f"_visits_{self.config.get('_node_id', 'router')}"
            visits = int(state.data.get(visit_key, 0) or 0) + 1
            state.data[visit_key] = visits
            logger.debug("[RouterNode] visitas=%d/%s node=%s", visits, max_visits, visit_key)
            if visits >= int(max_visits):
                logger.info("[RouterNode] max_visits=%s alcanzado → '%s'", max_visits, max_visits_route)
                state.data["route"] = max_visits_route
                return state

        # Reglas deterministas: se evalúan antes del LLM
        if pre_route_rules:
            route = _eval_pre_route_rules(pre_route_rules, state)
            if route:
                logger.info("[RouterNode] pre_route_rule → '%s'", route)
                state.data["route"] = route
                return state

        if not prompt:
            logger.warning("[RouterNode] Sin prompt — usando fallback '%s'", fallback)
            state.data["route"] = fallback
            return state

        prompt = interpolate(prompt, state)

        try:
            llm = _build_llm(model, temperature=0, json_out=False, router_strategy=router_strategy, max_tokens=10)
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user",   "content": f"Mensaje: {state.message}"},
            ]

            # Mismo reintento que LLMNode ante contenido vacío (bug real: la cascada
            # cloud-first a veces devuelve "" sin levantar excepción) — sin esto, un
            # route="" nunca matchea `routes` y cae siempre al fallback en silencio,
            # indistinguible de una clasificación genuina hacia esa rama.
            attempts = 0
            route = ""
            while True:
                attempts += 1
                result = await llm.ainvoke(messages)
                route = (result.content or "").strip().lower()
                if route:
                    break
                if attempts > _MAX_EMPTY_RETRIES:
                    detail = f"Router devolvió contenido vacío tras {attempts} intento(s)"
                    logger.error("[RouterNode] %s — fallback '%s'", detail, fallback)
                    _record_llm_error(state, "route", detail)
                    break
                logger.warning("[RouterNode] contenido vacío en intento %d, reintentando", attempts)

            if routes and route not in routes:
                logger.info("[RouterNode] respuesta '%s' no válida — usando fallback '%s'", route, fallback)
                route = fallback
            logger.info("[RouterNode] route → '%s' | msg: %.60s", route, state.message)
            state.data["route"] = route
        except Exception as e:
            logger.error("[RouterNode] Error: %s — fallback '%s'", e, fallback)
            state.data["route"] = fallback

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "prompt":          {"type": "textarea", "label": "Prompt del clasificador", "default": "", "rows": 7},
            "routes":          {"type": "list",     "label": "Rutas válidas",           "default": [], "hint": "Separadas por coma — ej: noticias,oficio,auspiciante"},
            "fallback":        {"type": "string",   "label": "Ruta por defecto",        "default": "", "hint": "Si el LLM responde algo inválido"},
            "model":       {"type": "select", "label": "Modelo", "default": "best:instruction|local-first",
                            "options": MODEL_OPTIONS},
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
