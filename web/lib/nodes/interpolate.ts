import type { FlowState } from "./state";

// TS port of interpolate() in pulpo/graphs/nodes/base.py, scoped to what the
// spike's nodes need: {{field}} placeholders resolved from state.data plus
// the meta fields (contact_name, contact_phone, bot_name, bot_id, canal).
// Conversation-array placeholders ({{conversation.last}} etc.) are out of
// scope for the spike -- neither api_trigger nor fetch_http's ported subset
// needs them.
function stringify(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function interpolate(template: string, state: FlowState): string {
  const meta: Record<string, string> = {
    contact_name: state.contactName || "",
    contact_phone: state.contactPhone || "",
    bot_name: state.botName || "",
    bot_id: state.botId || "",
    canal: state.canal || "",
  };

  const businessData: Record<string, string> = {};
  for (const [k, v] of Object.entries(state.data)) {
    if (v !== null && v !== undefined) businessData[k] = stringify(v);
  }

  const allFields = { ...businessData, ...meta };

  let result = template;
  for (let pass = 0; pass < 2; pass++) {
    const previous = result;
    result = result.replace(/\{\{(\w+)\}\}/g, (match, key: string) => {
      if (!(key in allFields)) return match; // deja {{unknown}} intacto
      return allFields[key];
    });
    if (result === previous) break;
  }
  return result;
}
