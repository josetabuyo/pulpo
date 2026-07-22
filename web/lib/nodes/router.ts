import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import { callLLM } from "./llm-client";
import type { FlowState } from "./state";

interface PreRouteRule {
  if_var?: string;
  not_in?: unknown[];
  then?: string;
}

// TS port of _eval_pre_route_rules (pulpo/graphs/nodes/router.py).
function evalPreRouteRules(rules: PreRouteRule[], state: FlowState): string | null {
  for (const rule of rules) {
    const varName = rule.if_var ?? "";
    const notIn = (rule.not_in ?? []).map(String);
    const then = rule.then ?? "";
    if (!varName || !then) continue;
    const value = String(state.data[varName] ?? "");
    if (value && !notIn.includes(value)) return then;
  }
  return null;
}

// TS port of RouterNode (pulpo/graphs/nodes/router.py).
export const routerNode: NodeDef = {
  label: "Router",
  color: "#854d0e",
  description: "Clasifica el mensaje con LLM y decide qué rama ejecutar.",
  configSchema: {},
  async run(state, config) {
    const prompt = (config.prompt as string) ?? "";
    const routes = (config.routes as string[]) ?? [];
    const fallback = (config.fallback as string) ?? routes[0] ?? "";
    const model = (config.model as string) ?? "best:instruction|local-first";
    const preRouteRules = (config.pre_route_rules as PreRouteRule[]) ?? [];
    const maxVisits = config.max_visits as number | undefined;
    const maxVisitsRoute = (config.max_visits_route as string) ?? "";

    if (preRouteRules.length) {
      const preRoute = evalPreRouteRules(preRouteRules, state);
      if (preRoute) {
        state.data.route = preRoute;
        return state;
      }
    }

    let route: string;
    if (!prompt) {
      route = fallback;
    } else {
      const promptI = interpolate(prompt, state);
      const { text, error } = await callLLM({
        systemPrompt: promptI,
        userMessage: `Mensaje: ${state.message}`,
        model,
        temperature: 0,
        maxTokens: 10,
      });
      if (error) {
        state.data._llm_errors = [...((state.data._llm_errors as unknown[]) ?? []), { output: "route", error }];
      }
      route = text.trim().toLowerCase();
      if (routes.length && !routes.includes(route)) route = fallback;
    }

    if (maxVisits && maxVisitsRoute && route === fallback) {
      const visitKey = `_visits_${(config._node_id as string) ?? "router"}`;
      const visits = Number(state.data[visitKey] ?? 0) + 1;
      state.data[visitKey] = visits;
      if (visits >= Number(maxVisits)) route = maxVisitsRoute;
    }

    state.data.route = route;
    return state;
  },
};
