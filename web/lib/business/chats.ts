import { and, asc, desc, eq, gt } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots, chatAccess, chatConfigs, chatConversations, chatMessages, flowRuns, flowRunSteps } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";
import { getPublishedAds } from "@/lib/business/chat-ads";
import { toPublicDirectoryDto } from "@/lib/business/chat-directory";
import { validateDirectoryConfig } from "@/lib/business/chat-directory-types";

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

// Mensaje de fábrica del banner "info trans" -- cualquier chat sin mensaje
// propio cargado usa este, así el rail nunca aparece vacío (mismo criterio
// que DEFAULT_BANNERS en ChatBanners.jsx).
export const DEFAULT_BANNER_MESSAGE = "Escribí lo que quieras, estamos para ayudarte 👋";

interface InfoBannerShape {
  enabled: boolean;
  message: string;
}

function toInfoBannerDto(raw: unknown): InfoBannerShape {
  const b = (raw ?? {}) as Partial<InfoBannerShape>;
  return {
    enabled: b.enabled !== false,
    message: b.message?.trim() || DEFAULT_BANNER_MESSAGE,
  };
}

function toConfigDto(row: ChatConfigRow) {
  return {
    id: row.id,
    bot_id: row.botId,
    flow_id: row.flowId,
    trigger_node_id: row.triggerNodeId,
    title: row.title,
    is_public: row.isPublic,
    open_login: row.openLogin,
    enabled: row.enabled,
    banners: row.banners ?? [],
    theme_vars: row.themeVars ?? {},
    custom_css: row.customCss ?? "",
    branding: row.branding ?? {},
    directory: row.directory ?? null,
    info_banner: toInfoBannerDto(row.infoBanner),
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
  openLogin?: boolean;
  enabled: boolean;
  banners?: unknown;
  themeVars?: unknown;
  customCss?: string;
  branding?: unknown;
  infoBanner?: unknown;
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
    openLogin: input.openLogin ?? false,
    enabled: input.enabled,
    banners: input.banners ?? [],
    themeVars: input.themeVars ?? {},
    customCss: input.customCss ?? "",
    branding: input.branding ?? {},
    infoBanner: input.infoBanner ?? null,
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
      openLogin: input.openLogin ?? false,
      enabled: input.enabled,
      banners: input.banners ?? [],
      themeVars: input.themeVars ?? {},
      customCss: input.customCss ?? "",
      branding: input.branding ?? {},
      infoBanner: input.infoBanner ?? null,
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
// `ads` (chat_ads publicadas, máx 4, nueva-primero) es el reemplazo de
// `banners` -- pero `banners` se mantiene siempre en la respuesta como
// fallback manual: si un chat viejo tiene `banners` cargado a mano y todavía
// no tiene ninguna fila en chat_ads, el widget lo sigue usando (ver
// ChatBanners.jsx) en vez de forzar una migración de datos existentes.
export async function toPublicConfigDto(row: ChatConfigRow) {
  const ads = await getPublishedAds(row.id);
  let directoryConfig = null;
  if (row.directory) {
    try {
      directoryConfig = validateDirectoryConfig(row.directory);
    } catch (err) {
      console.error(`[chats] directory config inválida en chat ${row.id}:`, err);
    }
  }
  return {
    title: row.title,
    banners: row.banners ?? [],
    ads,
    theme_vars: row.themeVars ?? {},
    custom_css: row.customCss ?? "",
    branding: row.branding ?? {},
    directory: toPublicDirectoryDto(directoryConfig),
    is_public: row.isPublic,
    open_login: row.openLogin,
    enabled: row.enabled,
    info_banner: toInfoBannerDto(row.infoBanner),
  };
}

// Actualiza SOLO el mensaje del banner info -- llamado desde el endpoint
// autenticado por X-Pulpo-Bot-Key (POST info-banner) para que Luganense
// pueda reportar algo sin tocar el resto de la config del chat.
export async function updateInfoBannerMessage(chatId: string, message: string, enabled = true) {
  const db = getDb();
  const existing = await getChatConfigRow(chatId);
  if (!existing) throw new NotFoundError(`Chat no encontrado: ${chatId}`);
  const infoBanner: InfoBannerShape = { enabled, message: message.trim() };
  await db.update(chatConfigs).set({ infoBanner, updatedAt: new Date() }).where(eq(chatConfigs.id, chatId));
  return infoBanner;
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

// Steps (`flow_run_steps`) de un run, SOLO si ese run pertenece a esta
// conversación (contact_identifier del run === contactIdentifier) -- scoped
// a propósito, no un `getRun` general: `GET /api/runs/{runId}` (mismo shape)
// exige sesión admin vía proxy.ts, así que un caller autenticado solo por
// X-Chat-Visitor (ver resolveChatCaller) no podría usarlo. Esto es lo que
// scripts/generate_e2e_report.py (vía tests/e2e/helpers.py::ChatConversation)
// necesita para validar el log de ejecución de SU PROPIA conversación,
// contra prod, sin login real -- ver app/api/chat/[botId]/[chatId]/
// conversations/[conversationId]/runs/[runId]/steps/route.ts.
export async function getOwnRunSteps(botId: string, contactIdentifier: string, runId: string) {
  const db = getDb();
  const [run] = await db
    .select({ id: flowRuns.runId, status: flowRuns.status })
    .from(flowRuns)
    .where(and(eq(flowRuns.runId, runId), eq(flowRuns.botId, botId), eq(flowRuns.contactPhone, contactIdentifier)));
  if (!run) return null;
  const rows = await db.select().from(flowRunSteps).where(eq(flowRunSteps.runId, runId)).orderBy(asc(flowRunSteps.id));
  return {
    // Status de ESTE run puntual -- distinto de getLastRunStatus (el run
    // más reciente del contacto, ambiguo justo en el instante del handoff:
    // ver ChatConversation.send_and_wait en tests/e2e/helpers.py, bug real
    // encontrado 2026-07-24 -- el run viejo sigue en "waiting_gate" un
    // instante después de que ya existe un run_id nuevo para el turno
    // siguiente).
    status: run.status,
    steps: rows.map((s) => ({
      id: s.id,
      node_id: s.nodeId,
      node_type: s.nodeType,
      started_at: s.startedAt,
      ended_at: s.endedAt,
      input_state: s.inputState,
      output_state: s.outputState,
      branch_taken: s.branchTaken,
      status: s.status,
      error_message: s.errorMessage,
    })),
  };
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
