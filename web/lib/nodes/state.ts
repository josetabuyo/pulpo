// TS port of pulpo/graphs/nodes/state.py (FlowState). Multimedia fields
// (message_type, attachment_path, group_sender) are out of scope -- see
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md (multimedia/contacts/WhatsApp
// deferred).
export interface FlowState {
  message: string;
  botId: string;
  botName: string;
  contactPhone: string;
  contactName: string;
  canal: "telegram" | "wavi" | "api";
  timestamp?: string;
  fromDeltaSync?: boolean;
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

export interface ConversationEntry {
  origin: "user" | "bot_reply" | string;
  content: string;
  type: string;
}

// TS port of append_conversation_entry (pulpo/graphs/nodes/state.py).
export function appendConversationEntry(state: FlowState, origin: string, content: string | null | undefined, msgType = "text") {
  if (!content) return;
  const conversation = (state.data.conversation as ConversationEntry[]) ?? [];
  conversation.push({ origin, content, type: msgType });
  state.data.conversation = conversation;
}

// TS port of record_bot_reply (pulpo/graphs/conversation.py).
export function recordBotReply(state: FlowState, content: string) {
  if ("conversation" in state.data) {
    appendConversationEntry(state, "bot_reply", content);
  }
}
