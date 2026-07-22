// TS port of pulpo/graphs/nodes/state.py (FlowState). Scoped to the fields
// the spike's two nodes (api_trigger, fetch_http) actually touch.
export interface FlowState {
  message: string;
  botId: string;
  botName: string;
  contactPhone: string;
  contactName: string;
  canal: "telegram" | "wavi" | "api";
  data: Record<string, unknown>;
}

export function createFlowState(partial: Partial<FlowState> & { message: string }): FlowState {
  return {
    botId: "",
    botName: "",
    contactPhone: "",
    contactName: "",
    canal: "api",
    data: {},
    ...partial,
  };
}
