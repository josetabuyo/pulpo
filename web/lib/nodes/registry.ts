import type { NodeDef } from "./base";
import { apiTriggerNode } from "./api-trigger";
import { fetchHttpNode } from "./fetch-http";
import { conditionNode } from "./condition";
import { routerNode } from "./router";
import { setStateNode } from "./set-state";
import { replyNode } from "./reply";
import { endConversationNode } from "./end-conversation";
import { llmNode } from "./llm";
import { metricNode } from "./metric";
import { subflowEndNode, subflowStartNode } from "./subflow";
import { messageTriggerNode, telegramTriggerNode } from "./trigger";

// TS port of NODE_REGISTRY (pulpo/graphs/nodes/__init__.py), scoped per
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md. `wait_user`, `gate`, and
// `nodo_flow` are deliberately NOT registered here even though they're
// ported: nodo_flow never executes (expanded away at compile time, see
// lib/flow/expand-node-flows.ts), and wait_user/gate both need to block the
// BFS loop itself (end this run without enqueuing neighbors) rather than run
// inside a step -- both are special-cased directly in workflows/run-flow.ts's
// BFS loop. Still out of scope: multimedia (transcribe_audio/save_attachment),
// contacts (check_contact/save_contact), Google Sheets (fetch_sheet/gsheet/
// search_sheet), vector_search, summarize, detect_conversation, message_join,
// whatsapp_trigger.
export const NODE_REGISTRY: Record<string, NodeDef> = {
  api_trigger: apiTriggerNode,
  fetch_http: fetchHttpNode,
  condition: conditionNode,
  router: routerNode,
  set_state: setStateNode,
  send_message: replyNode,
  end_conversation: endConversationNode,
  llm: llmNode,
  metric: metricNode,
  subflow_start: subflowStartNode,
  subflow_end: subflowEndNode,
  message_trigger: messageTriggerNode,
  telegram_trigger: telegramTriggerNode,
};
