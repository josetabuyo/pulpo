import {
  pgTable,
  text,
  boolean,
  timestamp,
  jsonb,
  serial,
  primaryKey,
  index,
} from "drizzle-orm/pg-core";

// Mirrors pulpo/core/db.py (SQLite, raw SQL) -- that file is the source of
// truth for this schema, not any Python model (there isn't one).

export const flows = pgTable("flows", {
  id: text("id").primaryKey(),
  botId: text("bot_id").notNull(),
  name: text("name").notNull(),
  definition: jsonb("definition").notNull(),
  connectionId: text("connection_id"),
  contactPhone: text("contact_phone"),
  active: boolean("active").notNull().default(true),
  contactFilter: jsonb("contact_filter"),
  flowKind: text("flow_kind"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});

export const flowVersions = pgTable("flow_versions", {
  id: serial("id").primaryKey(),
  flowId: text("flow_id").notNull(),
  name: text("name").notNull(),
  definition: jsonb("definition").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

export const flowRuns = pgTable("flow_runs", {
  runId: text("run_id").primaryKey(),
  flowId: text("flow_id").notNull(),
  botId: text("bot_id").notNull(),
  connectionId: text("connection_id"),
  startedAt: timestamp("started_at", { withTimezone: true }).defaultNow(),
  endedAt: timestamp("ended_at", { withTimezone: true }),
  // running | completed | waiting_gate | error | expired | handed_off
  status: text("status").notNull().default("running"),
  triggerData: jsonb("trigger_data"),
  contactPhone: text("contact_phone"),
  resumeNodeId: text("resume_node_id"),
  slotsJson: jsonb("slots_json"),
  isSim: boolean("is_sim").notNull().default(false),
  // not present in the Python schema -- lets us correlate a flow_run with
  // the Workflow DevKit run that executed it, for `npx workflow inspect run`.
  workflowRunId: text("workflow_run_id"),
});

// TS port of the state pulpo/graphs/nodes/gate.py keeps in-process
// (_GATE_STORE/_GATE_WAITING_RUNS) -- DB-backed since Vercel has no
// long-lived process to hold it. Accumulates one message per distinct
// trigger/path that reaches a `gate` node until `waitFor` (the node's
// in-degree) is reached; waitingRunId tracks the most recent run that
// blocked here so it can be closed ("handed_off") once the gate opens --
// same one-slot-only limitation as the Python original (an earlier blocked
// run gets silently orphaned if a later one overwrites this row before the
// gate opens).
export const gateWaits = pgTable(
  "gate_waits",
  {
    nodeId: text("node_id").notNull(),
    contactPhone: text("contact_phone").notNull(),
    messages: jsonb("messages").notNull().default([]),
    waitingRunId: text("waiting_run_id"),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (table) => [primaryKey({ columns: [table.nodeId, table.contactPhone] })]
);

// ─── Bots / connections ─────────────────────────────────────────────────
// Config-only port of pulpo/core/config.py (connections.json) -- no live
// process state (WhatsApp daemon / Telegram polling only exist locally).

export const bots = pgTable("bots", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  password: text("password").notNull(),
  // TS port of pulpo/core/paused.py's persisted flag (that file also
  // suppresses replies while still running flows for side effects like
  // summarize -- simplified here to just not dispatching at all while
  // paused, see app/api/telegram/webhook/[tokenId]/route.ts. Real but not
  // byte-for-byte the same semantics as Python.
  paused: boolean("paused").notNull().default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});

// Allowlist of which Google account can log into the portal of which bot --
// Paso 1 hacia "Pulpo Lite" (cliente ve solo su bot) / "Pulpo PRO" (ve varios
// bots), ambos el mismo mecanismo: cuantas filas tenga un email acá es lo que
// determina si ve uno o varios bots, no hay un rol separado para cada caso
// (ver web/auth.ts). Distinto de `googleConnections`, que es una cuenta de
// servicio de Google para que un bot lea/escriba un Sheet, no un login humano.
export const botUsers = pgTable(
  "bot_users",
  {
    botId: text("bot_id").notNull(),
    email: text("email").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => [primaryKey({ columns: [table.botId, table.email] })]
);

export const phoneConnections = pgTable("phone_connections", {
  number: text("number").primaryKey(),
  botId: text("bot_id").notNull(),
  alias: text("alias"),
  allowMass: boolean("allow_mass").notNull().default(false),
  defaultFilter: jsonb("default_filter"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

export const telegramConnections = pgTable("telegram_connections", {
  tokenId: text("token_id").primaryKey(),
  botId: text("bot_id").notNull(),
  token: text("token").notNull(),
  allowMass: boolean("allow_mass").notNull().default(false),
  // Snapshot de getMe() en el momento del alta -- no hay proceso vivo en
  // Vercel que lo mantenga actualizado, a diferencia del Python original
  // (que lo lee del client en memoria). Suficiente para mostrar @username
  // en el dashboard en vez del tokenId pelado.
  username: text("username"),
  botName: text("bot_name"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

// Contactos vistos por cada conexión de Telegram -- exclusivamente para que
// el nodo telegram_trigger resuelva include_all_known/include_unknown en su
// contact_filter. A propósito NO es la tabla `contacts` genérica del Python
// original (contact_channels/contacts) -- por decisión del usuario
// (2026-07-22) esta info es responsabilidad exclusiva del nodo de Telegram,
// sin dominio de contactos compartido en esta migración.
export const telegramKnownContacts = pgTable(
  "telegram_known_contacts",
  {
    tokenId: text("token_id").notNull(),
    chatId: text("chat_id").notNull(),
    username: text("username"),
    firstName: text("first_name"),
    firstSeenAt: timestamp("first_seen_at", { withTimezone: true }).defaultNow(),
    lastSeenAt: timestamp("last_seen_at", { withTimezone: true }).defaultNow(),
  },
  (table) => [primaryKey({ columns: [table.tokenId, table.chatId] })],
);

// Rate-limit de replies por (flow, chat_id) -- reemplaza FlowCooldown
// (pulpo/graphs/cooldown.py), que vive en memoria de proceso (no sirve en
// serverless: no hay proceso vivo entre invocaciones).
export const telegramTriggerCooldowns = pgTable(
  "telegram_trigger_cooldowns",
  {
    flowId: text("flow_id").notNull(),
    chatId: text("chat_id").notNull(),
    lastReplyAt: timestamp("last_reply_at", { withTimezone: true }).notNull(),
  },
  (table) => [primaryKey({ columns: [table.flowId, table.chatId] })],
);

export const googleConnections = pgTable("google_connections", {
  id: text("id").primaryKey(),
  botId: text("bot_id"),
  credentialsJson: text("credentials_json").notNull(),
  email: text("email").notNull(),
  label: text("label").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

// TS port of the `metrics` table (pulpo/core/db.py) -- MetricNode writes here.
export const metrics = pgTable("metrics", {
  id: serial("id").primaryKey(),
  botId: text("bot_id").notNull(),
  contactPhone: text("contact_phone"),
  contactName: text("contact_name"),
  canal: text("canal"),
  metricName: text("metric_name").notNull(),
  value: text("value"),
  metadata: text("metadata"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

export const flowRunSteps = pgTable("flow_run_steps", {
  id: serial("id").primaryKey(),
  runId: text("run_id")
    .notNull()
    .references(() => flowRuns.runId),
  nodeId: text("node_id").notNull(),
  nodeType: text("node_type").notNull(),
  startedAt: timestamp("started_at", { withTimezone: true }).defaultNow(),
  endedAt: timestamp("ended_at", { withTimezone: true }),
  inputState: jsonb("input_state"),
  outputState: jsonb("output_state"),
  branchTaken: text("branch_taken"),
  // ok | blocked | error
  status: text("status").notNull().default("ok"),
  // Mensaje de la excepción cuando status = "error" -- antes se descartaba en
  // runNodeStep (lib/flow/steps.ts), dejando el fallo sin rastro alguno.
  errorMessage: text("error_message"),
});

// TS port of pulpo/core/config.py::get_settings/update_settings (JSON file
// on the local Mac -- single-row table here, Vercel has no filesystem).
// Only field with a live frontend consumer today: wa_poll_interval_seconds,
// even though nothing in web/ reads it yet (no wavi poller in serverless) --
// see management/HANDOFF_VERCEL_DEEP_MIGRATION.md for why this is the only
// Fase-3 "Cargando..." panel actually worth porting right now.
export const settings = pgTable("settings", {
  id: text("id").primaryKey().default("singleton"),
  waPollIntervalSeconds: text("wa_poll_interval_seconds").notNull().default("300"),
});

// ─── Chats ("PulpoChat") ────────────────────────────────────────────────
// Vista "Chats": chat web embebible/standalone sobre el trigger HTTP.
// Ver management/HANDOFF_DASHBOARD_CHATS_VIEW.md (gitignoreado, no en el
// repo) para el diseño completo -- este comentario resume solo lo esencial.

// Config de un chat (N por bot, 2026-07-23: cada trigger_chat de la tab
// Chats es su propia fila). El chat existe solo si hay fila + enabled=true.
// `is_public` es un booleano explícito, no un sentinel `*` en una allowlist
// -- ver §2.1 del handoff para el razonamiento.
export const chatConfigs = pgTable(
  "chat_configs",
  {
    id: text("id").primaryKey(),
    botId: text("bot_id").notNull(),
    flowId: text("flow_id").notNull(),
    triggerNodeId: text("trigger_node_id").notNull(),
    title: text("title").notNull().default("PulpoChat"),
    isPublic: boolean("is_public").notNull().default(false),
    enabled: boolean("enabled").notNull().default(false),
    banners: jsonb("banners"),
    themeVars: jsonb("theme_vars"),
    customCss: text("custom_css"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (table) => [index("chat_configs_bot_id_idx").on(table.botId)],
);

// Allowlist de emails con derecho a CHATEAR (no a gestionar) cuando el chat
// no es público. Deliberadamente separada de `bot_users` (esa da acceso al
// dashboard del bot) -- ver §2.2 del handoff.
export const chatAccess = pgTable(
  "chat_access",
  {
    botId: text("bot_id").notNull(),
    email: text("email").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => [primaryKey({ columns: [table.botId, table.email] })],
);

// Identidad de cada conversación de chat -- `contact_identifier` (prefijo
// "chat:") es lo que viaja como contactPhone al motor de flows, así que dos
// conversaciones del mismo humano son dos contactos distintos (estilo
// ChatGPT: cada hilo es independiente). `owner_key` ("email:{email}" o
// "anon:{visitorKey}") es quién ve esta conversación en su sidebar.
export const chatConversations = pgTable("chat_conversations", {
  id: text("id").primaryKey(),
  botId: text("bot_id").notNull(),
  // A qué chat (chat_configs.id) pertenece esta conversación -- necesario
  // desde que un bot puede tener N chats (2026-07-23): sin esto no hay forma
  // de saber qué flow/trigger_node_id resolver al reanudar una conversación.
  chatConfigId: text("chat_config_id").notNull(),
  contactIdentifier: text("contact_identifier").notNull().unique(),
  ownerKey: text("owner_key").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  lastMessageAt: timestamp("last_message_at", { withTimezone: true }).defaultNow(),
});

// Transcript liviano del chat -- tabla propia, NO reconstruida desde
// flow_run_steps (ver §2.4 del handoff: flow_run_steps es jsonb pesado
// pensado para debug, y una conversación de chat abarca múltiples runs).
// Dos escritores: el POST de envío (role='user', antes de disparar el
// flow) y lib/nodes/reply.ts cuando canal==="chat" y to vacío (role='bot').
export const chatMessages = pgTable("chat_messages", {
  id: serial("id").primaryKey(),
  conversationId: text("conversation_id").notNull(),
  role: text("role").notNull(), // 'user' | 'bot'
  content: text("content").notNull(),
  runId: text("run_id"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});
