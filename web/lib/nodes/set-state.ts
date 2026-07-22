import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import type { FlowState } from "./state";

// TS port of SetStateNode (pulpo/graphs/nodes/set_state.py). The Python
// version can also target FlowState's fixed dataclass fields (e.g.
// `contact_name`) by name -- this port only writes to `state.data`, since
// the meta fields ported here (botId, contactPhone, etc.) are set once by
// the trigger and not meant to be reassigned mid-flow in this scoped-down
// engine.
export const setStateNode: NodeDef = {
  label: "Establecer estado",
  color: "#0891b2",
  description: "Escribe un valor fijo en un campo del estado del flow.",
  configSchema: {},
  async run(state: FlowState, config) {
    const field = ((config.field as string) ?? "").trim();
    const mode = (config.mode as string) ?? "set";
    if (!field) return state;

    if (mode === "increment") {
      const current = Number(state.data[field] ?? 0) || 0;
      state.data[field] = String(current + 1);
    } else {
      state.data[field] = interpolate((config.value as string) ?? "", state);
    }
    return state;
  },
};
