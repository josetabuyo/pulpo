import type { NodeDef } from "./base";

// TS port of SubflowStartNode/SubflowEndNode (pulpo/graphs/nodes/subflow_start.py,
// subflow_end.py). Both are pure passthroughs that DO execute (unlike
// nodo_flow, which never runs -- it's expanded away at compile time, see
// lib/flow/expand-node-flows.ts). They exist only to mark, explicitly and
// visibly in the editor canvas, the single entry point and one-or-more exit
// points of a sub-flow (flow_kind === "node_flow") -- expandNodeFlows()
// looks them up by type to know where to splice in the caller's edges.
export const subflowStartNode: NodeDef = {
  label: "Inicio de sub-flow",
  color: "#059669",
  description: "Marca el punto de entrada de un sub-flow (NodoFlow). Passthrough — no modifica el estado.",
  configSchema: {},
  async run(state) {
    return state;
  },
};

export const subflowEndNode: NodeDef = {
  label: "Fin de sub-flow",
  color: "#0d9488",
  description: "Marca un punto de salida de un sub-flow (NodoFlow). Passthrough — no modifica el estado.",
  configSchema: {},
  async run(state) {
    return state;
  },
};
