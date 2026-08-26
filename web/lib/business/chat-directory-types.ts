import { ValidationError } from "@/lib/business/bots";

// Shape de `chat_configs.directory` -- ver el comentario en lib/db/schema.ts.
// Genérico a propósito: nada acá menciona Luganense, para que otro cliente
// pueda tener su propia config con sus propios endpoints/campos/lead. Los
// namespaces de template soportados en `source.url`/`connect.lead.body` son
// EXACTAMENTE estos, ningún otro se resuelve:
//   {{q}}            -- solo en source.url, siempre URL-encoded
//   {{offset}}        -- solo en source.url, paginación -- ver "paginated" abajo
//   {{limit}}          -- solo en source.url, tamaño de página (= source.limit)
//   {{item.*}}       -- item ya normalizado por item_map (item.raw.* = crudo)
//   {{fields.*}}     -- lo que completó el usuario en el mini-form de connect
//   {{contact.id}} / {{contact.channel}} / {{contact.email}}
//   {{chat.bot_id}} / {{chat.id}} / {{chat.title}}
//   {{env.NOMBRE}}   -- resuelto server-side contra process.env, nunca literal
//
// Paginación (scroll infinito): opt-in por sección, sin campo de config
// nuevo -- si source.url incluye {{offset}}, la sección queda "paginated"
// (ver toPublicDirectoryDto) y el cliente pide la siguiente página al
// llegar al final de la lista. Si el upstream no soporta offset, simplemente
// no se incluye {{offset}} en la url y la sección se comporta como siempre
// (un solo fetch, sin scroll infinito). "Hay más" se infiere: si la página
// devuelve exactamente `limit` items, asumimos que puede haber más.

export interface DirectoryFieldDef {
  name: string;
  label: string;
  type: "text" | "tel" | "email" | "textarea" | "select";
  required?: boolean;
  placeholder?: string;
  options?: string[]; // solo para type: "select"
}

export interface DirectorySource {
  method: "GET";
  url: string;
  headers?: Record<string, string>;
  items_path: string; // resolveJsonPath hacia el array; "" = raíz
  item_map: {
    id: string;
    title: string;
    subtitle?: string;
    description?: string;
    image_url?: string;
    meta?: string;
    link?: string; // URL externa del item (ej. nota original) -- solo mode: "detail"
    // Opt-in genérico (no específico de ningún cliente): si está seteado,
    // searchSection pisa item.title con lo que haya en news_titles para
    // (title_cache_source, item.id), cuando exista una fila -- ver
    // scripts/generate-news-titles.ts. Pensado para fuentes cuyo título
    // crudo es basura (ej. Luganense: primera línea del post de Facebook).
    title_cache_source?: string;
  };
  limit?: number;
}

export interface DirectoryLead {
  method: "POST";
  url: string;
  headers?: Record<string, string>;
  success_codes: number[];
  body: Record<string, unknown>;
}

export interface DirectoryConnect {
  label: string;
  fields: DirectoryFieldDef[]; // [] = conecta directo, sin form intermedio
  confirm_text?: string;
  success_text?: string;
  lead: DirectoryLead;
}

// "connect" (default): item.click abre el mini-form y dispara un lead (comercios/servicios).
// "detail": item.click abre una vista de solo lectura (título/descripción/meta) + link externo
// (item_map.link) -- sin form ni lead, pensado para listas de solo-lectura tipo noticias.
export type DirectoryMode = "connect" | "detail";

export interface DirectorySection {
  id: string;
  label: string;
  icon?: string; // emoji corto opcional, se antepone al label del tab (ej. "📰")
  mode?: DirectoryMode;
  search_placeholder?: string;
  min_query_len?: number;
  empty_query?: "search" | "hide"; // "search": q="" igual se manda (listar todo); "hide": pedir texto primero
  source: DirectorySource;
  connect?: DirectoryConnect; // requerido si mode === "connect" (default), ignorado si mode === "detail"
}

export interface DirectoryConfig {
  version: 1;
  enabled: boolean;
  title?: string;
  sections: DirectorySection[];
}

// Item normalizado devuelto al cliente por searchSection -- image_url/meta/link
// pueden faltar si item_map no los mapea (p.ej. Luganense hoy no tiene foto).
export interface DirectoryItem {
  id: string;
  title: string;
  subtitle?: string;
  description?: string;
  image_url?: string;
  meta?: string;
  link?: string;
  raw: Record<string, unknown>;
  item_token: string;
}

// Subset expuesto al browser -- NUNCA source.*/lead.* (URLs, headers, body,
// credenciales). Ver chat-directory.ts::toPublicDirectoryDto.
export interface PublicDirectorySection {
  id: string;
  label: string;
  icon?: string;
  mode: DirectoryMode;
  search_placeholder?: string;
  min_query_len: number;
  empty_query: "search" | "hide";
  paginated: boolean; // true si source.url usa {{offset}} -- habilita scroll infinito client-side
  connect?: {
    label: string;
    fields: DirectoryFieldDef[];
    confirm_text?: string;
  };
}

export interface PublicDirectoryConfig {
  enabled: boolean;
  title: string;
  sections: PublicDirectorySection[];
}

export function isPaginatedSource(url: string): boolean {
  return /\{\{\s*offset\s*\}\}/.test(url);
}

const FIELD_TYPES = new Set(["text", "tel", "email", "textarea", "select"]);

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new ValidationError(msg);
}

// Solo https:// -- la config la define un admin del bot, no un usuario
// final, pero igual conviene no aceptar file://, http://, ni URLs
// apuntando a localhost/loopback/rangos privados desde el fetch server-side.
export function assertSafeUrl(rawUrl: string, label: string): void {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl.replace(/\{\{[^}]*\}\}/g, "x"));
  } catch {
    throw new ValidationError(`${label}: URL inválida`);
  }
  assert(parsed.protocol === "https:", `${label}: solo se permite https://`);
  const host = parsed.hostname.toLowerCase();
  const blocked =
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host === "0.0.0.0" ||
    /^127\./.test(host) ||
    /^10\./.test(host) ||
    /^192\.168\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[0-1])\./.test(host) ||
    host === "::1";
  assert(!blocked, `${label}: host no permitido`);
}

function validateFieldDef(f: unknown, sectionId: string): DirectoryFieldDef {
  assert(isRecord(f), `sección ${sectionId}: field inválido`);
  const name = f.name;
  const label = f.label;
  const type = f.type;
  assert(typeof name === "string" && name.trim(), `sección ${sectionId}: field.name requerido`);
  assert(typeof label === "string" && label.trim(), `sección ${sectionId}: field.label requerido`);
  assert(typeof type === "string" && FIELD_TYPES.has(type), `sección ${sectionId}: field.type inválido (${String(type)})`);
  const field: DirectoryFieldDef = { name, label, type: type as DirectoryFieldDef["type"] };
  if (typeof f.required === "boolean") field.required = f.required;
  if (typeof f.placeholder === "string") field.placeholder = f.placeholder;
  if (type === "select") {
    assert(Array.isArray(f.options) && f.options.every((o) => typeof o === "string"), `sección ${sectionId}: select requiere options: string[]`);
    field.options = f.options as string[];
  }
  return field;
}

function validateSource(s: unknown, sectionId: string): DirectorySource {
  assert(isRecord(s), `sección ${sectionId}: source requerido`);
  assert(s.method === "GET", `sección ${sectionId}: source.method debe ser "GET"`);
  assert(typeof s.url === "string" && s.url.trim(), `sección ${sectionId}: source.url requerido`);
  assertSafeUrl(s.url, `sección ${sectionId} source.url`);
  assert(typeof s.items_path === "string", `sección ${sectionId}: source.items_path requerido (puede ser "")`);
  assert(isRecord(s.item_map), `sección ${sectionId}: source.item_map requerido`);
  const im = s.item_map;
  assert(typeof im.id === "string" && im.id, `sección ${sectionId}: item_map.id requerido`);
  assert(typeof im.title === "string" && im.title, `sección ${sectionId}: item_map.title requerido`);
  const source: DirectorySource = {
    method: "GET",
    url: s.url,
    items_path: s.items_path,
    item_map: {
      id: im.id,
      title: im.title,
      subtitle: typeof im.subtitle === "string" ? im.subtitle : undefined,
      description: typeof im.description === "string" ? im.description : undefined,
      image_url: typeof im.image_url === "string" ? im.image_url : undefined,
      meta: typeof im.meta === "string" ? im.meta : undefined,
      link: typeof im.link === "string" ? im.link : undefined,
      title_cache_source: typeof im.title_cache_source === "string" ? im.title_cache_source : undefined,
    },
  };
  if (isRecord(s.headers)) source.headers = s.headers as Record<string, string>;
  if (typeof s.limit === "number" && s.limit > 0) source.limit = Math.min(s.limit, 100);
  return source;
}

function validateLead(l: unknown, sectionId: string): DirectoryLead {
  assert(isRecord(l), `sección ${sectionId}: connect.lead requerido`);
  assert(l.method === "POST", `sección ${sectionId}: lead.method debe ser "POST"`);
  assert(typeof l.url === "string" && l.url.trim(), `sección ${sectionId}: lead.url requerido`);
  assertSafeUrl(l.url, `sección ${sectionId} lead.url`);
  assert(
    Array.isArray(l.success_codes) && l.success_codes.length > 0 && l.success_codes.every((c) => typeof c === "number"),
    `sección ${sectionId}: lead.success_codes requerido (number[])`,
  );
  assert(isRecord(l.body), `sección ${sectionId}: lead.body requerido`);
  const lead: DirectoryLead = {
    method: "POST",
    url: l.url,
    success_codes: l.success_codes as number[],
    body: l.body,
  };
  if (isRecord(l.headers)) lead.headers = l.headers as Record<string, string>;
  return lead;
}

function validateConnect(c: unknown, sectionId: string): DirectoryConnect {
  assert(isRecord(c), `sección ${sectionId}: connect requerido`);
  assert(typeof c.label === "string" && c.label.trim(), `sección ${sectionId}: connect.label requerido`);
  assert(Array.isArray(c.fields), `sección ${sectionId}: connect.fields debe ser array`);
  const connect: DirectoryConnect = {
    label: c.label,
    fields: c.fields.map((f) => validateFieldDef(f, sectionId)),
    lead: validateLead(c.lead, sectionId),
  };
  if (typeof c.confirm_text === "string") connect.confirm_text = c.confirm_text;
  if (typeof c.success_text === "string") connect.success_text = c.success_text;
  return connect;
}

function validateSection(s: unknown): DirectorySection {
  assert(isRecord(s), "sección inválida");
  assert(typeof s.id === "string" && /^[a-z0-9_-]+$/.test(s.id), `section.id inválido: ${String(s.id)}`);
  // Reservado: tab incorporado (historial de conversaciones), no configurable
  // vía admin -- ver ChatDirectory.jsx CONVERSATIONS_TAB_ID.
  assert(s.id !== "conversaciones", `section.id "conversaciones" está reservado`);
  assert(typeof s.label === "string" && s.label.trim(), `sección ${String(s.id)}: label requerido`);
  assert(s.icon === undefined || (typeof s.icon === "string" && s.icon.length <= 8), `sección ${s.id}: icon debe ser un string corto (<=8 chars)`);
  assert(s.mode === undefined || s.mode === "connect" || s.mode === "detail", `sección ${s.id}: mode inválido (${String(s.mode)})`);
  const mode: DirectoryMode = s.mode === "detail" ? "detail" : "connect";
  const section: DirectorySection = {
    id: s.id,
    label: s.label,
    mode,
    source: validateSource(s.source, s.id),
  };
  if (typeof s.icon === "string") section.icon = s.icon;
  // mode "detail": item.click abre solo lectura, no hay form ni lead --
  // connect ni se valida ni se guarda, aunque venga en el raw.
  if (mode === "connect") section.connect = validateConnect(s.connect, s.id);
  if (typeof s.search_placeholder === "string") section.search_placeholder = s.search_placeholder;
  if (typeof s.min_query_len === "number") section.min_query_len = s.min_query_len;
  if (s.empty_query === "search" || s.empty_query === "hide") section.empty_query = s.empty_query;
  return section;
}

// Valida y normaliza una config cruda (de la DB o del admin) -- lanza
// ValidationError con un mensaje accionable en el primer problema encontrado.
export function validateDirectoryConfig(raw: unknown): DirectoryConfig {
  assert(isRecord(raw), "directory config debe ser un objeto");
  assert(raw.version === 1, `directory.version debe ser 1`);
  assert(typeof raw.enabled === "boolean", "directory.enabled requerido");
  assert(Array.isArray(raw.sections), "directory.sections debe ser array");
  const sections = raw.sections.map(validateSection);
  const ids = new Set(sections.map((s) => s.id));
  assert(ids.size === sections.length, "directory.sections: ids duplicados");
  const config: DirectoryConfig = { version: 1, enabled: raw.enabled, sections };
  if (typeof raw.title === "string") config.title = raw.title;
  return config;
}
