import { appendConversationEntry, type FlowState } from "@/lib/nodes/state";

// TS port of pulpo/graphs/conversation.py -- owns when a flow run
// accumulates data["conversation"]. Pure, no I/O -- safe to call directly
// from a "use workflow" function.

// First turn of a brand-new conversation: the message that triggered it.
// Idempotent (a message can match more than one flow) -- no-ops if
// "conversation" already exists.
export function startConversation(state: FlowState): void {
  if ("conversation" in state.data) return;
  appendConversationEntry(state, "user", state.message);
}

// Next turn when resuming a wait_user: the rest of the conversation already
// traveled in via the restored slots -- this only appends the new incoming message.
export function continueConversation(state: FlowState): void {
  appendConversationEntry(state, "user", state.message);
}
