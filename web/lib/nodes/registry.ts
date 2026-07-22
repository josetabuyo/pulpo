import type { NodeDef } from "./base";
import { apiTriggerNode } from "./api-trigger";
import { fetchHttpNode } from "./fetch-http";
import { conditionNode } from "./condition";
import { routerNode } from "./router";
import { setStateNode } from "./set-state";
import { replyNode } from "./reply";
import { endConversationNode } from "./end-conversation";
import { llmNode } from "./llm";
import { messageTriggerNode, telegramTriggerNode } from "./trigger";

// TS port of NODE_REGISTRY (pulpo/graphs/nodes/__init__.py), scoped per
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md: routing basics + llm. Out of
// scope (documented there): gate/wait_user (need createHook), nodo_flow/
// subflow_*, multimedia (transcribe_audio/save_attachment), contacts
// (check_contact/save_contact), Google Sheets (fetch_sheet/gsheet/
// search_sheet), vector_search, summarize, metric, detect_conversation,
// message_join, whatsapp_trigger.
export const NODE_REGISTRY: Record<string, NodeDef> = {
  api_trigger: apiTriggerNode,
  fetch_http: fetchHttpNode,
  condition: conditionNode,
  router: routerNode,
  set_state: setStateNode,
  send_message: replyNode,
  end_conversation: endConversationNode,
  llm: llmNode,
  message_trigger: messageTriggerNode,
  telegram_trigger: telegramTriggerNode,
};
