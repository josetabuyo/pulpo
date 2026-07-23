import { and, asc, desc, eq, gt } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots, chatAccess, chatConfigs, chatConversations, chatMessages, flowRuns } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// CRUD de las 4 tablas de "PulpoChat" (chat web sobre el trigger HTTP). Ver
// management/HANDOFF_DASHBOARD_CHATS_VIEW.md (gitignoreado) para el diseño
// completo -- acá solo la lógica de negocio; las rutas (app/api/bots/[botId]/
// chat-*/** y app/api/chat/[botId]/**) son finas y delegan todo acá.

// ─── Config (gestión, PRO/admin dueño del bot) ─────────────────────────

type ChatConfigRow = typeof chatConfigs.$inferSelect;

function toConfigDto(row: ChatConfigRow) {
  return {
    bot_id: row.botId,
    flow_id: row.flowId,
    trigger_node_id: row.triggerNodeId,
    title: row.title,
    is_public: row.isPublic,
    enabled: row.enabled,
    banners: row.banners ?? [],
    theme_vars: row.themeVars ?? {},
    custom_css: row.customCss ?? "",
    created_at: row.createdAt,
    updated_at: row.updatedAt,
  };
}

export async function getChatConfigRow(botId: string): Promise<ChatConfigRow | null> {
  const db = getDb();
  const [row] = await db.select().from(chatConfigs).where(eq(chatConfigs.botId, botId));
  return row ?? null;
}

export async function getChatConfig(botId: string) {
  const row = await getChatConfigRow(botId);
  return row ? toConfigDto(row) : null;
}

export interface ChatConfigInput {
  flowId: string;
  triggerNodeId: string;
  title?: string;
  isPublic: boolean;
  enabled: boolean;
  banners?: unknown;
  themeVars?: unknown;
  customCss?: string;
}

// Upsert -- 1 fila por bot. `isPublic`/`enabled` llegan ya normalizados del
// handler (azúcar `allowlist: ["*"]` -> is_public:true si algún día se
// agrega, ver §2.1 del handoff -- nunca persistir el sentinel, solo el bool).
export async function upsertChatConfig(botId: string, input: ChatConfigInput) {
  if (!input.flowId) throw new ValidationError("flow_id es requerido");
  if (!input.triggerNodeId) throw new ValidationError("trigger_node_id es requerido");

  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) throw new NotFoundError(`Bot no encontrada: ${botId}`);

  const patch = {
    botId,
    flowId: input.flowId,
    triggerNodeId: input.triggerNodeId,
    title: input.title?.trim() || "PulpoChat",
    isPublic: input.isPublic,
    enabled: input.enabled,
    banners: input.banners ?? [],
    themeVars: input.themeVars ?? {},
    customCss: input.customCss ?? "",
    updatedAt: new Date(),
  };

  await db
    .insert(chatConfigs)
    .values(patch)
    .onConflictDoUpdate({ target: chatConfigs.botId, set: patch });

  return getChatConfig(botId);
}

// Subset seguro para el runtime público -- NUNCA flow_id/trigger_node_id
// (identificarían internals del flow) ni allowlist (§4.2 del handoff).
export function toPublicConfigDto(row: ChatConfigRow) {
  return {
    title: row.title,
    banners: row.banners ?? [],
    theme_vars: row.themeVars ?? {},
    custom_css: row.customCss ?? "",
    is_public: row.isPublic,
    enabled: row.enabled,
  };
}

// ─── Allowlist de acceso al chat (chat_access, distinta de bot_users) ───

export async function listChatAccess(botId: string): Promise<string[]> {
  const db = getDb();
  const rows = await db.select({ email: chatAccess.email }).from(chatAccess).where(eq(chatAccess.botId, botId));
  return rows.map((r) => r.email);
}

export async function addChatAccess(botId: string, rawEmail: string): Promise<void> {
  const email = rawEmail.trim().toLowerCase();
  if (!email || !email.includes("@")) throw new ValidationError("Email inválido");
  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) throw new NotFoundError(`Bot no encontrada: ${botId}`);
  await db.insert(chatAccess).values({ botId, email }).onConflictDoNothing();
}

export async function removeChatAccess(botId: string, rawEmail: string): Promise<void> {
  const email = rawEmail.trim().toLowerCase();
  const db = getDb();
  await db.delete(chatAccess).where(and(eq(chatAccess.botId, botId), eq(chatAccess.email, email)));
}

// ¿Este email puede chatear (no gestionar) con el bot, cuando no es público?
// Nota: NO chequea bot_users acá -- eso lo resuelve el caller
// (resolveChatCaller en lib/auth/chat-access.ts), que ya tiene esa lista.
export async function hasChatAccess(botId: string, email: string): Promise<boolean> {
  const db = getDb();
  const [row] = await db
    .select()
    .from(chatAccess)
    .where(and(eq(chatAccess.botId, botId), eq(chatAccess.email, email.toLowerCase())));
  return Boolean(row);
}

// ─── Conversaciones (vista de gestión: todas las del bot) ──────────────

export async function listBotChats(botId: string) {
  const db = getDb();
  const rows = await db
    .select({
      id: chatConversations.id,
      ownerKey: chatConversations.ownerKey,
      createdAt: chatConversations.createdAt,
      lastMessageAt: chatConversations.lastMessageAt,
    })
    .from(chatConversations)
    .where(eq(chatConversations.botId, botId))
    .orderBy(desc(chatConversations.lastMessageAt));
  return rows.map((r) => ({
    id: r.id,
    owner_key: r.ownerKey,
    created_at: r.createdAt,
    last_message_at: r.lastMessageAt,
  }));
}

export async function getConversation(botId: string, conversationId: string) {
  const db = getDb();
  const [row] = await db
    .select()
    .from(chatConversations)
    .where(and(eq(chatConversations.id, conversationId), eq(chatConversations.botId, botId)));
  return row ?? null;
}

export async function listConversationMessages(conversationId: string, afterId?: number) {
  const db = getDb();
  const condition = afterId
    ? and(eq(chatMessages.conversationId, conversationId), gt(chatMessages.id, afterId))
    : eq(chatMessages.conversationId, conversationId);
  const rows = await db.select().from(chatMessages).where(condition).orderBy(asc(chatMessages.id));
  return rows.map((r) => ({
    id: r.id,
    role: r.role,
    content: r.content,
    run_id: r.runId,
    created_at: r.createdAt,
  }));
}

// Último run que tocó esta conversación (por contact_identifier) -- para
// exponer run_status en el GET de mensajes (§3 del handoff: waiting_gate
// habilita el input de nuevo, completed/handed_off también, running lo
// deja deshabilitado con el indicador "...").
export async function getLastRunStatus(botId: string, contactIdentifier: string): Promise<string | null> {
  const db = getDb();
  const [row] = await db
    .select({ status: flowRuns.status })
    .from(flowRuns)
    .where(and(eq(flowRuns.botId, botId), eq(flowRuns.contactPhone, contactIdentifier)))
    .orderBy(desc(flowRuns.startedAt))
    .limit(1);
  return row?.status ?? null;
}

// ─── Conversaciones (runtime: propias del caller) ───────────────────────

export async function listOwnConversations(botId: string, ownerKey: string) {
  const db = getDb();
  const rows = await db
    .select({
      id: chatConversations.id,
      createdAt: chatConversations.createdAt,
      lastMessageAt: chatConversations.lastMessageAt,
    })
    .from(chatConversations)
    .where(and(eq(chatConversations.botId, botId), eq(chatConversations.ownerKey, ownerKey)))
    .orderBy(desc(chatConversations.lastMessageAt));
  return rows.map((r) => ({ id: r.id, created_at: r.createdAt, last_message_at: r.lastMessageAt }));
}

export async function createConversation(botId: string, ownerKey: string) {
  const db = getDb();
  const id = crypto.randomUUID();
  const contactIdentifier = `chat:${id}`;
  await db.insert(chatConversations).values({ id, botId, contactIdentifier, ownerKey });
  return { id, created_at: new Date(), last_message_at: new Date() };
}

export async function insertUserMessage(conversationId: string, content: string) {
  const db = getDb();
  await db.insert(chatMessages).values({ conversationId, role: "user", content });
  await db
    .update(chatConversations)
    .set({ lastMessageAt: new Date() })
    .where(eq(chatConversations.id, conversationId));
}

// Llamado desde lib/nodes/reply.ts cuando canal==="chat" y `to` vacío --
// best-effort igual que el envío de Telegram (si falla, loguear y no
// abortar el flow, ver ese archivo).
export async function insertBotMessage(contactIdentifier: string, content: string, runId?: string) {
  const db = getDb();
  const [conv] = await db
    .select({ id: chatConversations.id })
    .from(chatConversations)
    .where(eq(chatConversations.contactIdentifier, contactIdentifier));
  if (!conv) {
    console.error(`[chats] insertBotMessage: sin chat_conversations para contact_identifier=${contactIdentifier}`);
    return;
  }
  await db.insert(chatMessages).values({ conversationId: conv.id, role: "bot", content, runId });
  await db.update(chatConversations).set({ lastMessageAt: new Date() }).where(eq(chatConversations.id, conv.id));
}
