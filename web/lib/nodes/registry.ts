import type { NodeDef } from "./base";
import { apiTriggerNode } from "./api-trigger";
import { fetchHttpNode } from "./fetch-http";

// TS port of NODE_REGISTRY (pulpo/graphs/nodes/__init__.py), scoped to the
// two node types this spike validates end-to-end. The remaining ~23 Python
// node types are ported incrementally after the spike confirms the fit.
export const NODE_REGISTRY: Record<string, NodeDef> = {
  api_trigger: apiTriggerNode,
  fetch_http: fetchHttpNode,
};
