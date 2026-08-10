import crypto from "node:crypto";
import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { chatConfigs } from "@/lib/db/schema";
import { ValidationError } from "@/lib/business/bots";
import { resolveJsonPath, SENTINEL } from "@/lib/nodes/json-path";
import {
  validateDirectoryConfig,
  type DirectoryConfig,
  type DirectoryItem,
  type DirectorySection,
  type PublicDirectoryConfig,
} from "@/lib/business/chat-directory-types";

// Camino paralelo al chat conversacional (2026-08-09): dispara el mismo tipo
// de "lead" que hoy arma el nodo HTTP del flow, pero desde una UI de
// catálogo (rail izquierdo, ver ChatDirectory.jsx), sin pasar por la
// conversación. Genérico: nada acá conoce a Luganense -- todo sale de
// `chat_configs.directory`, validada por chat-directory-types.ts.
//
// Namespaces de template soportados -- ver el comentario de arriba de
// chat-directory-types.ts para la lista completa.

const ITEM_TOKEN_TTL_MS = 15 * 60 * 1000;
const FETCH_TIMEOUT_MS = 8000;
const MAX_FIELD_LEN = 500;
const ENV_ALLOW_PREFIX = "PULPO_DIR_";

// AUTH_SECRET (NextAuth) es el secreto de instancia que SIEMPRE está seteado
// -- JWT_SECRET_KEY es opcional en algunos ambientes (ver lib/auth/jwt.ts,
// que sí exige el suyo porque firma tokens de sesión propios). Cualquiera de
// los dos sirve acá: solo necesitamos un secreto de instancia estable para
// el HMAC del item_token, no algo exclusivo de JWT.
function getInstanceSecret(): string {
  const secret = process.env.JWT_SECRET_KEY || process.env.AUTH_SECRET;
  if (!secret) throw new Error("JWT_SECRET_KEY / AUTH_SECRET no está seteado");
  return secret;
}

// ─── item_token: HMAC-firmado, evita que un cliente forje un item/lead ────
// que nunca vino de una búsqueda real (ver connectSection). TTL corto: el
// token solo tiene que sobrevivir "el usuario mira la lista y toca Conectar".

export function signItemToken(chatConfigId: string, sectionId: string, itemId: string): string {
  const expiresAt = Date.now() + ITEM_TOKEN_TTL_MS;
  const payload = JSON.stringify({ c: chatConfigId, s: sectionId, i: itemId, e: expiresAt });
  const payloadB64 = Buffer.from(payload).toString("base64url");
  const sig = crypto.createHmac("sha256", getInstanceSecret()).update(payloadB64).digest("base64url");
  return `${payloadB64}.${sig}`;
}

export function verifyItemToken(token: string, chatConfigId: string, sectionId: string, itemId: string): boolean {
  const [payloadB64, sig] = String(token || "").split(".");
  if (!payloadB64 || !sig) return false;
  const expectedSig = crypto.createHmac("sha256", getInstanceSecret()).update(payloadB64).digest("base64url");
  const a = Buffer.from(sig);
  const b = Buffer.from(expectedSig);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return false;
  let payload: { c: string; s: string; i: string; e: number };
  try {
    payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
  } catch {
    return false;
  }
  return payload.c === chatConfigId && payload.s === sectionId && payload.i === itemId && payload.e > Date.now();
}

// ─── Template rendering (contexto plano, NO FlowState) ────────────────────

export interface TemplateCtx {
  q?: string;
  item?: Record<string, unknown>;
  fields?: Record<string, unknown>;
  contact?: Record<string, unknown>;
  chat?: Record<string, unknown>;
  env?: Record<string, unknown>;
}

const TEMPLATE_RE = /\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g;

function lookupTemplate(ctx: TemplateCtx, path: string): { found: boolean; value?: unknown } {
  const [ns, ...rest] = path.split(".");
  if (ns === "q") {
    if (rest.length) return { found: false };
    return { found: ctx.q !== undefined, value: ctx.q };
  }
  const namespaces: Record<string, Record<string, unknown> | undefined> = {
    item: ctx.item,
    fields: ctx.fields,
    contact: ctx.contact,
    chat: ctx.chat,
    env: ctx.env,
  };
  if (!(ns in namespaces)) return { found: false };
  const value = resolveJsonPath(namespaces[ns] ?? {}, rest.join("."));
  if (value === SENTINEL) return { found: false };
  return { found: true, value };
}

function stringifyTemplateValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export class UnresolvedTemplateError extends ValidationError {}

// strict=true -> {{...}} sin resolver lanza UnresolvedTemplateError (usado en
// connect.lead.body: nunca mandamos un placeholder crudo al POST del cliente).
// strict=false -> deja el placeholder intacto (usado en source.url, donde
// solo {{q}} está garantizado y el resto es best-effort).
export function renderTemplate(tpl: string, ctx: TemplateCtx, opts: { urlEncode?: boolean; strict?: boolean } = {}): string {
  return tpl.replace(TEMPLATE_RE, (match, path: string) => {
    const { found, value } = lookupTemplate(ctx, path);
    if (!found) {
      if (opts.strict) throw new UnresolvedTemplateError(`template sin resolver: {{${path}}}`);
      return match;
    }
    const str = stringifyTemplateValue(value);
    return opts.urlEncode ? encodeURIComponent(str) : str;
  });
}

export function renderDeep(value: unknown, ctx: TemplateCtx, opts: { strict?: boolean } = {}): unknown {
  if (typeof value === "string") return renderTemplate(value, ctx, opts);
  if (Array.isArray(value)) return value.map((v) => renderDeep(v, ctx, opts));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, renderDeep(v, ctx, opts)]));
  }
  return value;
}

function resolveEnvNamespace(headers?: Record<string, string>): Record<string, string> {
  // Allowlist: solo env vars con prefijo PULPO_DIR_ son alcanzables desde
  // {{env.*}} -- una config de directorio nunca puede leer un secreto
  // arbitrario del proceso (DATABASE_URL, JWT_SECRET_KEY, etc).
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith(ENV_ALLOW_PREFIX) && typeof value === "string") {
      env[key.slice(ENV_ALLOW_PREFIX.length)] = value;
    }
  }
  void headers;
  return env;
}

// ─── Config CRUD ────────────────────────────────────────────────────────

type ChatConfigRow = typeof chatConfigs.$inferSelect;

export async function getDirectoryConfig(chatConfigId: string): Promise<DirectoryConfig | null> {
  const db = getDb();
  const [row] = await db.select({ directory: chatConfigs.directory }).from(chatConfigs).where(eq(chatConfigs.id, chatConfigId));
  if (!row?.directory) return null;
  try {
    return validateDirectoryConfig(row.directory);
  } catch (err) {
    console.error(`[chat-directory] config inválida guardada para ${chatConfigId}:`, err);
    return null;
  }
}

export async function setDirectoryConfig(chatConfigId: string, raw: unknown): Promise<DirectoryConfig> {
  const config = validateDirectoryConfig(raw);
  const db = getDb();
  await db.update(chatConfigs).set({ directory: config, updatedAt: new Date() }).where(eq(chatConfigs.id, chatConfigId));
  return config;
}

// Sanitiza -- NUNCA exponer source.*/lead.* (URLs, headers, body, env) al
// browser. Este es el único punto por el que `directory` llega al widget
// (vía toPublicConfigDto en chats.ts), así que un error acá es una fuga de
// credenciales/URLs internas directa.
export function toPublicDirectoryDto(config: DirectoryConfig | null): PublicDirectoryConfig {
  if (!config) return { enabled: false, title: "Directorio", sections: [] };
  return {
    enabled: config.enabled,
    title: config.title ?? "Directorio",
    sections: config.sections.map((s) => ({
      id: s.id,
      label: s.label,
      mode: s.mode ?? "connect",
      search_placeholder: s.search_placeholder,
      min_query_len: s.min_query_len ?? 0,
      empty_query: s.empty_query ?? "search",
      connect: s.connect
        ? {
            label: s.connect.label,
            fields: s.connect.fields,
            confirm_text: s.connect.confirm_text,
          }
        : undefined,
    })),
  };
}

function getSectionOrThrow(config: DirectoryConfig, sectionId: string): DirectorySection {
  const section = config.sections.find((s) => s.id === sectionId);
  if (!section) throw new ValidationError(`sección no encontrada: ${sectionId}`);
  return section;
}

interface MappedItemFields {
  id: string;
  title: string;
  subtitle?: string;
  description?: string;
  image_url?: string;
  meta?: string;
  link?: string;
}

// Compartido entre searchSection (arma el DirectoryItem que ve el cliente) y
// connectSection (re-deriva item.title/subtitle/etc para el template del
// lead a partir del `raw` que el cliente reenvía -- nunca confiamos en un
// `title` mandado suelto por el cliente, se recalcula server-side con el
// mismo item_map que usó la búsqueda).
function mapItemFields(raw: unknown, section: DirectorySection): MappedItemFields | null {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const map = section.source.item_map;
  const id = resolveJsonPath(raw, map.id);
  const title = resolveJsonPath(raw, map.title);
  if (id === SENTINEL || title === SENTINEL) return null;
  const get = (path?: string) => {
    if (!path) return undefined;
    const v = resolveJsonPath(raw, path);
    return v === SENTINEL || v === null || v === undefined ? undefined : String(v);
  };
  return {
    id: String(id),
    title: String(title),
    subtitle: get(map.subtitle),
    description: get(map.description),
    image_url: get(map.image_url),
    meta: get(map.meta),
    link: get(map.link),
  };
}

function normalizeItem(raw: unknown, section: DirectorySection, chatConfigId: string): DirectoryItem | null {
  const mapped = mapItemFields(raw, section);
  if (!mapped) return null;
  return {
    ...mapped,
    raw: raw as Record<string, unknown>,
    item_token: signItemToken(chatConfigId, section.id, mapped.id),
  };
}

// ─── Búsqueda (server-side, evita CORS y no expone credenciales upstream) ─

export async function searchSection(
  chatConfigId: string,
  sectionId: string,
  q: string,
): Promise<{ items: DirectoryItem[]; error?: string }> {
  const config = await getDirectoryConfig(chatConfigId);
  if (!config || !config.enabled) return { items: [], error: "directory no configurado" };

  let section: DirectorySection;
  try {
    section = getSectionOrThrow(config, sectionId);
  } catch (err) {
    return { items: [], error: err instanceof Error ? err.message : String(err) };
  }

  const url = renderTemplate(section.source.url, { q: q ?? "" }, { urlEncode: true });
  const headers = section.source.headers
    ? Object.fromEntries(Object.entries(section.source.headers).map(([k, v]) => [k, renderTemplate(v, { env: resolveEnvNamespace() })]))
    : undefined;

  let raw: string;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await fetch(url, { method: "GET", headers, signal: controller.signal });
      if (!res.ok) {
        console.error(`[chat-directory] search upstream HTTP ${res.status}: ${url}`);
        return { items: [], error: `upstream respondió ${res.status}` };
      }
      raw = await res.text();
    } finally {
      clearTimeout(timer);
    }
  } catch (err) {
    console.error(`[chat-directory] search fetch error: ${url}`, err);
    return { items: [], error: "no se pudo consultar el directorio" };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    console.error(`[chat-directory] search: respuesta no es JSON válido: ${url}`);
    return { items: [], error: "respuesta upstream inválida" };
  }

  const list = resolveJsonPath(parsed, section.source.items_path);
  if (!Array.isArray(list)) {
    console.error(`[chat-directory] search: items_path "${section.source.items_path}" no resolvió a un array`);
    return { items: [], error: "respuesta upstream inesperada" };
  }

  const limit = section.source.limit ?? 30;
  const items = list
    .slice(0, limit)
    .map((it) => normalizeItem(it, section, chatConfigId))
    .filter((it): it is DirectoryItem => it !== null);

  return { items };
}

// ─── Connect (dispara el lead) ─────────────────────────────────────────

export interface ConnectContact {
  id: string;
  channel: string;
  email?: string;
}

export interface ConnectInput {
  itemId: string;
  itemToken: string;
  itemRaw?: Record<string, unknown>; // sombra client-side del item, solo para item.* -- id validado contra el token, no confiar en el resto sin más
  fields: Record<string, unknown>;
  contact: ConnectContact;
}

export function validateFields(section: DirectorySection, input: Record<string, unknown>): Record<string, string> {
  if (!section.connect) throw new ValidationError(`sección ${section.id} es de solo lectura, no admite conectar`);
  const out: Record<string, string> = {};
  for (const field of section.connect.fields) {
    const raw = input[field.name];
    const value = raw === null || raw === undefined ? "" : String(raw).trim();
    if (field.required && !value) throw new ValidationError(`campo requerido: ${field.label}`);
    if (value.length > MAX_FIELD_LEN) throw new ValidationError(`campo demasiado largo: ${field.label}`);
    if (field.type === "select" && value && !field.options?.includes(value)) {
      throw new ValidationError(`valor inválido para ${field.label}`);
    }
    out[field.name] = value;
  }
  return out;
}

export async function connectSection(
  chatConfigId: string,
  sectionId: string,
  input: ConnectInput,
  chat: { bot_id: string; id: string; title: string },
): Promise<{ ok: true; message: string }> {
  const config = await getDirectoryConfig(chatConfigId);
  if (!config || !config.enabled) throw new ValidationError("directory no configurado");
  const section = getSectionOrThrow(config, sectionId);
  const connectConfig = section.connect;
  if (!connectConfig) throw new ValidationError(`sección ${sectionId} es de solo lectura, no admite conectar`);

  if (!verifyItemToken(input.itemToken, chatConfigId, sectionId, input.itemId)) {
    throw new ValidationError("item_token inválido o expirado -- volvé a buscar");
  }

  const fields = validateFields(section, input.fields);

  // Re-deriva title/subtitle/etc del `raw` que reenvía el cliente con el
  // mismo item_map de la sección -- nunca confiamos en un item.title que
  // venga suelto del cliente (ver mapItemFields).
  const mapped = mapItemFields(input.itemRaw ?? {}, section);
  if (!mapped || mapped.id !== input.itemId) {
    throw new ValidationError("item inválido -- volvé a buscar y probá de nuevo");
  }

  const ctx: TemplateCtx = {
    item: { ...mapped, raw: input.itemRaw ?? {} },
    fields,
    contact: { id: input.contact.id, channel: input.contact.channel, email: input.contact.email },
    chat,
    env: resolveEnvNamespace(),
  };

  const lead = connectConfig.lead;
  const url = renderTemplate(lead.url, ctx, { strict: false });
  const body = renderDeep(lead.body, ctx, { strict: true });
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(lead.headers ?? {}) };

  let res: Response;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  } catch (err) {
    console.error(`[chat-directory] connect fetch error: ${url}`, err);
    throw new ValidationError("no se pudo conectar -- intentá de nuevo");
  }

  if (!lead.success_codes.includes(res.status)) {
    const text = await res.text().catch(() => "");
    console.error(`[chat-directory] connect upstream HTTP ${res.status}: ${url} -- ${text.slice(0, 300)}`);
    throw new ValidationError(`no se pudo conectar (upstream ${res.status})`);
  }

  const message = renderTemplate(connectConfig.success_text ?? "Listo, ya avisamos.", ctx, { strict: false });
  return { ok: true, message };
}

export type { ChatConfigRow };
