import { and, desc, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flowRuns, flows, telegramKnownContacts, telegramTriggerCooldowns } from "@/lib/db/schema";

// TS port of graphs/trigger_match.py + graphs/cooldown.py, scoped to
// telegram_trigger only (see management/HANDOFF_VERCEL_DEEP_MIGRATION.md).
// Deliberate scope decision (2026-07-22, user): contact_filter matching here
// is exclusively the telegram_trigger node's own business -- no shared
// `contacts`/`contact_channels` domain like the Python original. `included`/
// `excluded` are raw Telegram chat_ids (no name resolution), and
// "known contact" means "this chat_id has messaged this connection before",
// tracked in `telegram_known_contacts` (populated by the webhook itself).
// Multi-flow dispatch is kept: every active flow whose telegram_trigger
// matches fires, same as dispatch_message() iterating all of a bot's flows.

export interface ContactFilter {
  include_all_known?: boolean;
  include_unknown?: boolean;
  included?: string[];
  excluded?: string[];
}

// Mirrors _passes_contact_filter's included/excluded/include_all/include_unknown
// branch (the name-resolution branch is out of scope here, see module docstring).
// A configured-but-empty filter is default-deny -- matches the Python original
// (an untouched node-types.json default of all-false/empty lets nobody through
// until the flow author explicitly opts a chat_id in).
export function matchesContactFilter(
  filter: ContactFilter | null | undefined,
  chatId: string,
  isKnown: boolean,
  allowMass: boolean,
): boolean {
  if (!filter) return true; // sin filtro configurado -- pasa cualquiera (legacy, ver trigger_match.py)

  const excluded = filter.excluded ?? [];
  const included = filter.included ?? [];
  let incAll = Boolean(filter.include_all_known);
  let incUnknown = Boolean(filter.include_unknown);
  if ((incAll || incUnknown) && !allowMass) {
    incAll = false;
    incUnknown = false;
  }

  if (excluded.includes(chatId)) return false;
  if (included.includes(chatId)) return true;
  if (incAll && isKnown) return true;
  if (incUnknown && !isKnown) return true;
  return false;
}

// Mirrors _matches_pattern (trigger_match.py) -- an invalid regex doesn't block the flow.
export function matchesMessagePattern(pattern: string | undefined, message: string): boolean {
  if (!pattern || !message) return true;
  try {
    return new RegExp(pattern, "i").test(message);
  } catch {
    return true;
  }
}

export async function isKnownContact(tokenId: string, chatId: string): Promise<boolean> {
  const db = getDb();
  const [row] = await db
    .select()
    .from(telegramKnownContacts)
    .where(and(eq(telegramKnownContacts.tokenId, tokenId), eq(telegramKnownContacts.chatId, chatId)));
  return Boolean(row);
}

export async function touchKnownContact(
  tokenId: string,
  chatId: string,
  username: string | null,
  firstName: string | null,
): Promise<void> {
  const db = getDb();
  await db
    .insert(telegramKnownContacts)
    .values({ tokenId, chatId, username, firstName })
    .onConflictDoUpdate({
      target: [telegramKnownContacts.tokenId, telegramKnownContacts.chatId],
      set: { lastSeenAt: new Date(), username, firstName },
    });
}

// Mirrors FlowCooldown.is_active (graphs/cooldown.py), persisted instead of
// in-memory -- serverless has no long-lived process for a dict to survive in.
export async function isCooldownActive(flowId: string, chatId: string, hours: number): Promise<boolean> {
  if (hours <= 0) return false;
  const db = getDb();
  const [row] = await db
    .select()
    .from(telegramTriggerCooldowns)
    .where(and(eq(telegramTriggerCooldowns.flowId, flowId), eq(telegramTriggerCooldowns.chatId, chatId)));
  if (!row) return false;
  const elapsedHours = (Date.now() - row.lastReplyAt.getTime()) / 3_600_000;
  return elapsedHours < hours;
}

export async function markCooldown(flowId: string, chatId: string): Promise<void> {
  const db = getDb();
  await db
    .insert(telegramTriggerCooldowns)
    .values({ flowId, chatId, lastReplyAt: new Date() })
    .onConflictDoUpdate({
      target: [telegramTriggerCooldowns.flowId, telegramTriggerCooldowns.chatId],
      set: { lastReplyAt: new Date() },
    });
}

export interface TriggerMatch {
  flowId: string;
  nodeId: string;
}

interface FlowDefinitionNode {
  id: string;
  type: string;
  config?: Record<string, unknown>;
}

// Telegram session id convention (web/lib/business/bots.ts's listBots(),
// matches pulpo/business/bots.py::list_bots): "{botId}-tg-{tokenId}". This
// is what a telegram_trigger node's `connection_id` config actually holds
// (verified against the real luganense flow's definition) -- NOT the bare
// tokenId. Mirrors trigger_match.py's select_trigger() dual check exactly
// (older flows configured with just the bare bot_id as connection_id still
// match any of that bot's telegram sessions).
function connectionMatches(requiredConnection: string, sessionId: string): boolean {
  return requiredConnection === sessionId || sessionId.startsWith(`${requiredConnection}-tg-`);
}

// Mirrors select_trigger() + the cooldown gate in execute_flow() (compiler.py),
// but iterates ALL active flows of the bot instead of stopping at the first
// match -- multi-flow dispatch is a deliberate requirement here (user,
// 2026-07-22): if more than one flow's telegram_trigger matches, all of them
// fire, with no conflict resolution needed between them.
export async function findMatchingTriggers(
  botId: string,
  tokenId: string,
  chatId: string,
  message: string,
  isKnown: boolean,
  allowMass: boolean,
): Promise<TriggerMatch[]> {
  const sessionId = `${botId}-tg-${tokenId}`;
  const db = getDb();
  const rows = await db.select().from(flows).where(and(eq(flows.botId, botId), eq(flows.active, true)));

  const matches: TriggerMatch[] = [];
  for (const flow of rows) {
    const definition = flow.definition as { nodes?: FlowDefinitionNode[] };
    const triggerNodes = (definition.nodes ?? []).filter((n) => n.type === "telegram_trigger");

    for (const node of triggerNodes) {
      const config = node.config ?? {};
      // Pausa por-nodo (2026-07-23, tab "Triggers"): un trigger pausado no
      // matchea nunca, sin afectar a otros triggers del mismo flow ni de
      // otros flows -- ver web/lib/business/flows.ts::setFlowNodeConfig.
      if (config.paused) continue;
      const requiredConnection = (config.connection_id as string | undefined) ?? "";
      if (!requiredConnection || !connectionMatches(requiredConnection, sessionId)) continue;
      if (!matchesContactFilter(config.contact_filter as ContactFilter | undefined, chatId, isKnown, allowMass)) continue;
      if (!matchesMessagePattern(config.message_pattern as string | undefined, message)) continue;

      const hours = Number(config.cooldown_hours ?? 4);
      if (await isCooldownActive(flow.id, chatId, hours)) continue;
      if (hours > 0) await markCooldown(flow.id, chatId);

      matches.push({ flowId: flow.id, nodeId: node.id });
      break; // primer trigger que matchea gana DENTRO de este flow, como select_trigger
    }
  }
  return matches;
}

// ─── Reanudación de wait_user (TS port de la mitad "dispatcher" de
// dispatch_message en pulpo/graphs/compiler.py) ─────────────────────────────

export async function getWaitingGateRun(botId: string, contactPhone: string) {
  const db = getDb();
  const [run] = await db
    .select()
    .from(flowRuns)
    .where(and(eq(flowRuns.botId, botId), eq(flowRuns.contactPhone, contactPhone), eq(flowRuns.status, "waiting_gate")))
    .orderBy(desc(flowRuns.startedAt))
    .limit(1);
  return run ?? null;
}

// "handed_off" (no "completed"): este run nunca llegó a un final natural,
// quedó parqueado en wait_user -- el run nuevo (resumeNodeId) es el que sigue.
export async function endFlowRunHandedOff(runId: string): Promise<void> {
  const db = getDb();
  await db.update(flowRuns).set({ status: "handed_off", endedAt: new Date() }).where(eq(flowRuns.runId, runId));
}

// Mirrors resume_wait_user_run's slot-restore logic (compiler.py): drop the
// internal-only flags the pause left behind, and reset loop-visit counters
// if the conversation went idle >30min (avoids an instant "agotado" when the
// user picks up an old session).
export function restoreSlotsForResume(slotsJson: unknown, startedAt: Date): Record<string, unknown> {
  const saved: Record<string, unknown> = { ...((slotsJson as Record<string, unknown>) ?? {}) };
  delete saved._has_waiting_gate;
  delete saved._gate_blocked;
  const ageMinutes = (Date.now() - startedAt.getTime()) / 60_000;
  if (ageMinutes > 30) {
    for (const key of Object.keys(saved)) {
      if (key.startsWith("_visits_")) delete saved[key];
    }
  }
  return saved;
}

// Valida un token contra la API real de Telegram (getMe) y devuelve el
// snapshot que se guarda en telegramConnections.username/botName -- el
// Python original nunca valida el token al momento del alta (recién falla
// cuando intenta levantar el client de polling), pero acá no hay proceso
// vivo que lo intente por nosotros, así que validar en el alta es la única
// forma de no guardar un token roto silenciosamente.
export async function getTelegramBotInfo(
  token: string,
): Promise<{ username: string; botName: string }> {
  const res = await fetch(`https://api.telegram.org/bot${token}/getMe`);
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.description || `Token inválido (HTTP ${res.status})`);
  }
  return { username: data.result.username ?? "", botName: data.result.first_name ?? "" };
}

// Único lugar que sabe cómo se envía un mensaje de Telegram -- mismo patrón
// que lib/nodes/llm-client.ts (HTTP puro, sin SDK).
export async function sendTelegramMessage(token: string, chatId: string, text: string): Promise<void> {
  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
  if (!res.ok) {
    throw new Error(`telegram sendMessage -> HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }
}
