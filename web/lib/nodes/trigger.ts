import type { NodeDef } from "./base";

// TS port of BaseTriggerNode/BaseMessageTriggerNode (pulpo/graphs/nodes/base_trigger.py,
// message_trigger.py, telegram_trigger.py). Triggers are guards -- filtering
// (trigger_match.py: connection_id, contact_filter, message_pattern,
// cooldown_hours) isn't ported yet (single-flow dispatch only, see handoff
// doc), so run() is the same no-op passthrough as the Python side once a
// trigger has already been selected.
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
