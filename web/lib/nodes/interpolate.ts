import type { ConversationEntry, FlowState } from "./state";

// TS port of interpolate() in pulpo/graphs/nodes/base.py.
const CONV_ORIGIN_LABELS: Record<string, string> = { user: "Usuario", bot_reply: "Bot" };

function formatConversation(entries: ConversationEntry[]): string {
  return entries
    .map((entry) => `${CONV_ORIGIN_LABELS[entry.origin] ?? entry.origin}: ${entry.content ?? ""}`)
    .join("\n");
}

// {{conversation}} | {{conversation.first}} | {{conversation.last}} | {{conversation[i]}}
// with optional .origin / .content suffix (default: .content)
const CONVERSATION_RE = /\{\{conversation(?:\.(first|last)|\[(-?\d+)\])?(?:\.(origin|content))?\}\}/g;

function replaceConversation(template: string, state: FlowState): string {
  const entries = (state.data.conversation as ConversationEntry[]) ?? [];
  return template.replace(CONVERSATION_RE, (match, firstLast, idxStr, field) => {
    if (firstLast === undefined && idxStr === undefined) return formatConversation(entries);
    const idx = firstLast === "first" ? 0 : firstLast === "last" ? -1 : Number(idxStr);
    const entry = entries.at(idx);
    if (!entry) return match; // deja el placeholder intacto
    return String((entry as unknown as Record<string, string>)[field ?? "content"] ?? "");
  });
}

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
    result = replaceConversation(result, state);
    result = result.replace(/\{\{(\w+)\}\}/g, (match, key: string) => {
      if (!(key in allFields)) return match; // deja {{unknown}} intacto
      return allFields[key];
    });
    if (result === previous) break;
  }
  return result;
}
