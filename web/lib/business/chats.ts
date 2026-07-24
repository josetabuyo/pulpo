import { and, asc, desc, eq, gt } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots, chatAccess, chatConfigs, chatConversations, chatMessages, flowRuns } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// CRUD de las 4 tablas de "PulpoChat" (chat web sobre nodos trigger de
// mensaje). Ver management/HANDOFF_DASHBOARD_CHATS_VIEW.md (gitignoreado)
// para el diseño original -- acá solo la lógica de negocio; las rutas
// (app/api/bots/[botId]/chat-*/** y app/api/chat/[botId]/[chatId]/**) son
// finas y delegan todo acá.
//
// 2026-07-23: un bot puede tener N chats (antes era 1 fila por bot, ver
// docs/adr en el worktree vercel-deep-migration) -- cada chat es su propia
// fila de chat_configs con `id` propio, apuntando a un flow/trigger_node_id
// fijo (normalmente un nodo trigger_chat, ver lib/nodes/trigger-chat.ts).

// ─── Config (gestión, PRO/admin dueño del bot) ─────────────────────────

type ChatConfigRow = typeof chatConfigs.$inferSelect;

function toConfigDto(row: ChatConfigRow) {
  return {
    id: row.id,
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

// Chat puntual por id -- NO filtra por botId (el caller debe validar
// pertenencia si le importa, ver resolveChatCaller en lib/auth/chat-access.ts).
export async function getChatConfigRow(chatId: string): Promise<ChatConfigRow | null> {
  const db = getDb();
  const [row] = await db.select().from(chatConfigs).where(eq(chatConfigs.id, chatId));
  return row ?? null;
}

export async function getChatConfig(chatId: string) {
  const row = await getChatConfigRow(chatId);
  return row ? toConfigDto(row) : null;
}

export async function listChatConfigs(botId: string) {
  const db = getDb();
  const rows = await db
    .select()
    .from(chatConfigs)
    .where(eq(chatConfigs.botId, botId))
    .orderBy(desc(chatConfigs.createdAt));
  return rows.map(toConfigDto);
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

function validateChatConfigInput(input: ChatConfigInput) {
  if (!input.flowId) throw new ValidationError("flow_id es requerido");
  if (!input.triggerNodeId) throw new ValidationError("trigger_node_id es requerido");
}

// Alta -- `isPublic`/`enabled` llegan ya normalizados del handler (azúcar
// `allowlist: ["*"]` -> is_public:true si algún día se agrega, ver §2.1 del
// handoff -- nunca persistir el sentinel, solo el bool).
export async function createChatConfig(botId: string, input: ChatConfigInput) {
  validateChatConfigInput(input);

  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) throw new NotFoundError(`Bot no encontrada: ${botId}`);

  const id = crypto.randomUUID();
  await db.insert(chatConfigs).values({
    id,
    botId,
    flowId: input.flowId,
    triggerNodeId: input.triggerNodeId,
    title: input.title?.trim() || "PulpoChat",
    isPublic: input.isPublic,
    enabled: input.enabled,
    banners: input.banners ?? [],
    themeVars: input.themeVars ?? {},
    customCss: input.customCss ?? "",
  });

  return getChatConfig(id);
}

export async function updateChatConfig(chatId: string, botId: string, input: ChatConfigInput) {
  validateChatConfigInput(input);

  const db = getDb();
  const existing = await getChatConfigRow(chatId);
  if (!existing || existing.botId !== botId) throw new NotFoundError(`Chat no encontrado: ${chatId}`);

  await db
    .update(chatConfigs)
    .set({
      flowId: input.flowId,
      triggerNodeId: input.triggerNodeId,
      title: input.title?.trim() || "PulpoChat",
      isPublic: input.isPublic,
      enabled: input.enabled,
      banners: input.banners ?? [],
      themeVars: input.themeVars ?? {},
      customCss: input.customCss ?? "",
      updatedAt: new Date(),
    })
    .where(eq(chatConfigs.id, chatId));

  return getChatConfig(chatId);
}

// Borra solo la config -- las conversaciones/mensajes son dominio de
// ejecuciones de flow y quedan intactas (pedido explícito del usuario,
// 2026-07-23: "borrar un chat no debería borrar la historia").
export async function deleteChatConfig(chatId: string, botId: string): Promise<void> {
  const db = getDb();
  const existing = await getChatConfigRow(chatId);
  if (!existing || existing.botId !== botId) throw new NotFoundError(`Chat no encontrado: ${chatId}`);
  await db.delete(chatConfigs).where(eq(chatConfigs.id, chatId));
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
// Bot-scoped a propósito (no por chat individual): un email autorizado al
// bot puede chatear con cualquiera de sus chats privados.

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

// ─── Conversaciones (vista de gestión: todas las del bot, opcionalmente
// filtradas a un chat puntual para la vista embebida por-chat) ──────────

export async function listBotChats(botId: string, chatConfigId?: string) {
  const db = getDb();
  const condition = chatConfigId
    ? and(eq(chatConversations.botId, botId), eq(chatConversations.chatConfigId, chatConfigId))
    : eq(chatConversations.botId, botId);
  const rows = await db
    .select({
      id: chatConversations.id,
      chatConfigId: chatConversations.chatConfigId,
      ownerKey: chatConversations.ownerKey,
      createdAt: chatConversations.createdAt,
      lastMessageAt: chatConversations.lastMessageAt,
    })
    .from(chatConversations)
    .where(condition)
    .orderBy(desc(chatConversations.lastMessageAt));
  return rows.map((r) => ({
    id: r.id,
    chat_config_id: r.chatConfigId,
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

// ─── Conversaciones (runtime: propias del caller, de UN chat puntual) ──

export async function listOwnConversations(botId: string, chatConfigId: string, ownerKey: string) {
  const db = getDb();
  const rows = await db
    .select({
      id: chatConversations.id,
      createdAt: chatConversations.createdAt,
      lastMessageAt: chatConversations.lastMessageAt,
    })
    .from(chatConversations)
    .where(
      and(
        eq(chatConversations.botId, botId),
        eq(chatConversations.chatConfigId, chatConfigId),
        eq(chatConversations.ownerKey, ownerKey),
      ),
    )
    .orderBy(desc(chatConversations.lastMessageAt));
  return rows.map((r) => ({ id: r.id, created_at: r.createdAt, last_message_at: r.lastMessageAt }));
}

export async function createConversation(botId: string, chatConfigId: string, ownerKey: string) {
  const db = getDb();
  const id = crypto.randomUUID();
  const contactIdentifier = `chat:${id}`;
  await db.insert(chatConversations).values({ id, botId, chatConfigId, contactIdentifier, ownerKey });
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
