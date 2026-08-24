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
    const disabledRoutes = new Set((config.disabled_routes as string[]) ?? []);
    const activeRoutes = routes.filter((r) => !disabledRoutes.has(r));

    if (preRouteRules.length) {
      const preRoute = evalPreRouteRules(preRouteRules, state);
      // Rama deshabilitada desde el editor (toggle "Ramas") -- se ignora
      // como si la regla no existiera, sigue al flujo normal de clasificación.
      if (preRoute && !disabledRoutes.has(preRoute)) {
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
        // Reasoning-capable models (increasingly the default across
        // providers' cascades, e.g. Groq's openai/gpt-oss-* and qwen3.6-*)
        // spend completion tokens on a <think>/reasoning preamble before
        // the actual route word. 10 was too tight -- it truncated mid-think
        // for every reasoning model, leaving unstripped "<think>..." text
        // (or an empty content field, for models that put reasoning in a
        // separate field) that silently missed the activeRoutes check below
        // and fell back to `fallback` with NO error signal (found via a
        // real incident, 2026-08-24: a plumbing request kept misrouting to
        // "noticias"). 500 gives room for a full reasoning pass -- cheap on
        // Groq's LPU hardware (sub-second even at this length).
        maxTokens: 500,
      });
      if (error) {
        state.data._llm_errors = [...((state.data._llm_errors as unknown[]) ?? []), { output: "route", error }];
      }
      route = text.trim().toLowerCase();
      // Two different reasons a route can miss activeRoutes -- only the
      // first is a real failure worth logging. A route the LLM correctly
      // named but that's disabled from the editor ("Ramas" toggle) is
      // expected control flow, not an error -- `disabled_routes` is a
      // deliberate business gate (e.g. Luganense's "producto") -- logging
      // that as an _llm_errors entry would fail no_llm_errors checks on
      // every disabled-route fallback, which isn't a bug.
      if (routes.length && !routes.includes(route)) {
        state.data._llm_errors = [
          ...((state.data._llm_errors as unknown[]) ?? []),
          { output: "route", error: `respuesta no es una ruta válida: ${JSON.stringify(text).slice(0, 200)}` },
        ];
        route = fallback;
      } else if (activeRoutes.length && !activeRoutes.includes(route)) {
        route = fallback;
      }
    }

    if (maxVisits && maxVisitsRoute && !disabledRoutes.has(maxVisitsRoute) && route === fallback) {
      const visitKey = `_visits_${(config._node_id as string) ?? "router"}`;
      const visits = Number(state.data[visitKey] ?? 0) + 1;
      state.data[visitKey] = visits;
      if (visits >= Number(maxVisits)) route = maxVisitsRoute;
    }

    if (disabledRoutes.has(route)) route = fallback;
    state.data.route = route;
    return state;
  },
};
