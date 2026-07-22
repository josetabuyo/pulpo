import type { NodeDef } from "./base";

// TS port of BaseTriggerNode/BaseMessageTriggerNode (pulpo/graphs/nodes/base_trigger.py,
// message_trigger.py, telegram_trigger.py). Triggers are guards -- run() is
// a no-op passthrough, same as the Python side once a trigger has already
// been selected. For telegram_trigger, the actual filtering (connection_id,
// contact_filter, message_pattern, cooldown_hours -- lib/business/telegram.ts's
// findMatchingTriggers, scoped port of trigger_match.py/cooldown.py) happens
// BEFORE the workflow starts, in app/api/telegram/webhook/[tokenId]/route.ts
// -- by the time this node runs, a match has already been picked.
// message_trigger (generic/legacy) still has no matching implemented.
const triggerNode: NodeDef = {
  label: "Trigger",
  color: "#166534",
  description: "Punto de entrada de un flow.",
  configSchema: {},
  async run(state) {
    return state;
  },
};

export const messageTriggerNode = triggerNode;
export const telegramTriggerNode = triggerNode;
