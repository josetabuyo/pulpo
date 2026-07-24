import type { NodeDef } from "./base";

// TS port of EndConversationNode (pulpo/graphs/nodes/end_conversation.py).
// Scoped down: the Python version also closes DB rows left in
// waiting_gate/open_conversations by gate/wait_user -- neither is ported yet
// (see handoff doc), so there's nothing to close here. This just marks the
// state flag other nodes/the caller can check, same contract as the Python
// side's `state.data["_conversation_closed"]`.
export const endConversationNode: NodeDef = {
  label: "Cerrar conversación",
  color: "#be123c",
  description: "Cierra explícitamente la conversación actual. El próximo mensaje del contacto abrirá un flow nuevo.",
  configSchema: {},
  async run(state) {
    state.data._conversation_closed = true;
    return state;
  },
};
