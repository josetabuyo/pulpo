import type { FlowState } from "./state";

// TS port of BaseNode (pulpo/graphs/nodes/base.py). SIM_MODE is intentionally
// omitted -- in-band simulation (management/HANDOFF_SIMULACION_V2.md) is out
// of scope for this spike.
export interface ConfigField {
  type: "string" | "url" | "select" | "bool" | "float" | "json" | "list";
  label: string;
  default?: unknown;
  options?: string[];
  required?: boolean;
  hint?: string;
}

export interface NodeDef {
  label: string;
  color: string;
  description: string;
  configSchema: Record<string, ConfigField>;
  run(state: FlowState, config: Record<string, unknown>): Promise<FlowState>;
}
