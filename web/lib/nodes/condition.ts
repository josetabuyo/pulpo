import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import type { FlowState } from "./state";

// TS port of ConditionNode (pulpo/graphs/nodes/condition.py).
interface Rule {
  var?: string;
  op?: string;
  value?: unknown;
  values?: unknown[];
  then?: string;
}

function evalRule(rule: Rule, state: FlowState): boolean {
  const varName = interpolate(rule.var ?? "", state);
  if (!varName) return false;
  const value = String(state.data[varName] ?? "");
  const op = rule.op ?? "equals";

  switch (op) {
    case "equals":
      return value === String(rule.value ?? "");
    case "not_equals":
      return value !== String(rule.value ?? "");
    case "in":
      return (rule.values ?? []).map(String).includes(value);
    case "not_in":
      return !(rule.values ?? []).map(String).includes(value);
    case "empty":
      return value === "";
    case "not_empty":
      return value !== "";
    case "contains":
      return value.includes(String(rule.value ?? ""));
    default:
      return false;
  }
}

export const conditionNode: NodeDef = {
  label: "Condición",
  color: "#92400e",
  description: "Evalúa reglas sobre variables del estado y decide qué rama ejecutar. Sin LLM — decisión pura.",
  configSchema: {},
  async run(state, config) {
    const rules = (config.rules as Rule[]) ?? [];
    const fallback = (config.fallback as string) ?? "";
    const maxVisits = config.max_visits as number | undefined;
    const maxVisitsRoute = (config.max_visits_route as string) ?? "";

    let route = fallback;
    for (const rule of rules) {
      if (evalRule(rule, state)) {
        if (rule.then) {
          route = rule.then;
          break;
        }
      }
    }

    if (maxVisits && maxVisitsRoute && route === fallback) {
      const visitKey = `_visits_${(config._node_id as string) ?? "condition"}`;
      const visits = Number(state.data[visitKey] ?? 0) + 1;
      state.data[visitKey] = visits;
      if (visits >= Number(maxVisits)) route = maxVisitsRoute;
    }

    state.data.route = route;
    return state;
  },
};
