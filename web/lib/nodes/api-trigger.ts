import type { NodeDef } from "./base";

// TS port of ApiTriggerNode (pulpo/graphs/nodes/api_trigger.py). The Python
// version is a BaseTriggerNode subclass matched by the compiler's trigger
// selection (trigger_match.py) before the BFS starts. This spike's executor
// (lib/flow/execute.ts) always starts at an explicit entryNodeId instead of
// doing trigger matching, so here the node is just a passthrough marking the
// flow's HTTP entry point -- same runtime behavior as the Python node has
// once selected (it doesn't mutate state).
export const apiTriggerNode: NodeDef = {
  label: "API Trigger",
  color: "#7c3aed",
  description: "Punto de entrada via HTTP. Activa el flow con un POST a /api/flows/{flowId}/trigger/{nodeId}.",
  configSchema: {},
  async run(state) {
    return state;
  },
};
