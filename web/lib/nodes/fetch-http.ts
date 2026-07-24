import type { NodeDef } from "./base";
import type { ConversationEntry, FlowState } from "./state";
import { interpolate } from "./interpolate";

// TS port of FetchHttpNode (pulpo/graphs/nodes/fetch_http.py) -- full port,
// not the scoped-down spike version: array_input (per-item fan-out),
// extract_fields (JSON path extraction), route_output (HTTP-status-based
// routing) are all needed by the real luganense flow (see
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md).

const MAX_ARRAY_ITEMS = 10;
const ITEM_FIELD_RE = /\{\{item\.([a-zA-Z0-9_]+)\}\}/g;
const ITEM_RE = /\{\{item\}\}/g;
const UNRESOLVED_TEMPLATE_RE = /\{\{.*?\}\}/;
const SENTINEL = Symbol("not-found");

function recordFetchError(state: FlowState, url: string, error: string, statusCode?: number | null) {
  const errors = (state.data._fetch_errors as unknown[]) ?? [];
  errors.push({ url, status_code: statusCode ?? null, error });
  state.data._fetch_errors = errors;
}

function resolveJsonPath(parsed: unknown, path: string): unknown {
  let current: unknown = parsed;
  for (const part of path.split(".")) {
    if (current !== null && typeof current === "object" && !Array.isArray(current)) {
      const obj = current as Record<string, unknown>;
      if (!(part in obj)) return SENTINEL;
      current = obj[part];
    } else if (Array.isArray(current)) {
      if (!/^-?\d+$/.test(part)) return SENTINEL;
      const idx = Number(part);
      const realIdx = idx < 0 ? current.length + idx : idx;
      if (realIdx < 0 || realIdx >= current.length) return SENTINEL;
      current = current[realIdx];
    } else {
      return SENTINEL;
    }
  }
  return current;
}

function applyExtractFields(state: FlowState, raw: string | null, extractFields: Record<string, string>) {
  if (!raw) return;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    console.warn("[fetch_http] extract_fields: respuesta no es JSON válido, se omite");
    return;
  }
  for (const [key, path] of Object.entries(extractFields)) {
    const value = resolveJsonPath(parsed, path);
    if (value === SENTINEL || value === null || value === undefined) continue;
    state.data[key] = value as never;
  }
}

function interpolateDeep(value: unknown, state: FlowState): unknown {
  if (typeof value === "string") return interpolate(value, state);
  if (Array.isArray(value)) return value.map((v) => interpolateDeep(v, state));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, interpolateDeep(v, state)]),
    );
  }
  return value;
}

function fillItemTemplate(urlTemplate: string, item: unknown): string {
  let url = urlTemplate.replace(ITEM_FIELD_RE, (_match, field: string) => {
    const value = item !== null && typeof item === "object" ? (item as Record<string, unknown>)[field] ?? "" : "";
    return encodeURIComponent(String(value));
  });
  if (item === null || typeof item !== "object") {
    url = url.replace(ITEM_RE, encodeURIComponent(String(item)));
  }
  return url;
}

// Mirrors FetchHttpNode._resolve_url: {{query}}/{{message}} have their own
// fallback chain (state.data.query -> state.data.necesidad -> last
// conversation turn -> raw message), url-encoded before the generic
// interpolate() pass.
function resolveUrl(urlTemplate: string, state: FlowState): string {
  const conversation = (state.data.conversation as ConversationEntry[]) ?? [];
  const lastMessage = conversation.length ? conversation[conversation.length - 1]?.content ?? "" : state.message || "";
  const queryValue = (state.data.query as string) || (state.data.necesidad as string) || lastMessage || "";

  let url = urlTemplate
    .replaceAll("{{query}}", encodeURIComponent(String(queryValue)))
    .replaceAll("{{message}}", encodeURIComponent(String(lastMessage)))
    .replaceAll("{query}", encodeURIComponent(String(queryValue)))
    .replaceAll("{message}", encodeURIComponent(String(lastMessage)));

  return interpolate(url, state);
}

interface RequestResult {
  raw: string | null;
  statusCode: number | null;
}

async function doRequest(method: string, url: string, extract: string, state: FlowState, body?: unknown): Promise<RequestResult> {
  if (UNRESOLVED_TEMPLATE_RE.test(url)) {
    console.error(`[fetch_http] URL con placeholder {{...}} sin resolver: ${url}`);
    recordFetchError(state, url, "unresolved {{...}} placeholder in URL");
    return { raw: null, statusCode: null };
  }
  try {
    const res = await fetch(url, {
      method,
      headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
      body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      recordFetchError(state, url, `HTTP ${res.status}: ${text.slice(0, 200)}`, res.status);
      return { raw: null, statusCode: res.status };
    }
    if (extract === "json" || extract === "html") {
      return { raw: await res.text(), statusCode: res.status };
    }
    const raw = await res.text();
    const text = raw.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    return { raw: text.slice(0, 5000), statusCode: res.status };
  } catch (err) {
    recordFetchError(state, url, err instanceof Error ? err.message : String(err));
    return { raw: null, statusCode: null };
  }
}

function routeFor(statusCodes: Array<number | null>, successCodes: Set<number>, config: Record<string, unknown>): string {
  const routeSuccess = (config.route_success as string) || "ok";
  const routeNoError = (config.route_no_error as string) || "no_error";
  const routeError = (config.route_error as string) || "error";

  if (statusCodes.some((code) => code === null || code >= 400)) return routeError;
  if (statusCodes.every((code) => code !== null && successCodes.has(code))) return routeSuccess;
  return routeNoError;
}

export const fetchHttpNode: NodeDef = {
  label: "Fetch HTTP",
  color: "#1e40af",
  description: "Hace uno o más llamados HTTP (GET o POST) a una URL externa y guarda la respuesta como contexto.",
  configSchema: {
    url: { type: "string", label: "URL", default: "" },
    method: { type: "select", label: "Método HTTP", default: "GET", options: ["GET", "POST"] },
    body: { type: "json", label: "Body (solo POST)", default: {} },
    extract: { type: "select", label: "Formato de respuesta", default: "text", options: ["text", "json", "html"] },
    output: { type: "string", label: "Variable de salida", default: "context" },
  },
  async run(state, config) {
    const urlTemplate = (config.url as string) || "";
    const method = ((config.method as string) || "GET").toUpperCase();
    const extract = (config.extract as string) || "text";
    const output = (config.output as string) || "context";
    const arrayInput = ((config.array_input as string) || "").trim();

    if (!urlTemplate) {
      console.warn("[fetch_http] sin url configurada");
      return state;
    }

    const routeOutput = Boolean(config.route_output);
    const successCodes = new Set<number>((config.success_codes as number[]) ?? [200, 201]);
    const statusCodes: Array<number | null> = [];

    const items = arrayInput ? state.data[arrayInput] : undefined;

    if (arrayInput && Array.isArray(items) && items.length) {
      if (items.length > MAX_ARRAY_ITEMS) {
        console.warn(`[fetch_http] array_input '${arrayInput}' tiene ${items.length} items — truncado a ${MAX_ARRAY_ITEMS}`);
      }
      const results: Array<string | null> = [];
      for (const item of items.slice(0, MAX_ARRAY_ITEMS)) {
        const itemUrl = resolveUrl(fillItemTemplate(urlTemplate, item), state);
        const { raw, statusCode } = await doRequest(method, itemUrl, extract, state);
        results.push(raw);
        statusCodes.push(statusCode);
      }
      state.data[output] = results;
    } else {
      const url = resolveUrl(urlTemplate, state);
      const body = method === "POST" ? interpolateDeep(config.body ?? {}, state) : undefined;
      const { raw, statusCode } = await doRequest(method, url, extract, state, body);
      statusCodes.push(statusCode);
      state.data[output] = raw;

      const extractFields = (config.extract_fields as Record<string, string>) ?? {};
      if (extractFields && Object.keys(extractFields).length && extract === "json") {
        applyExtractFields(state, raw, extractFields);
      }
    }

    if (routeOutput) {
      state.data.route = routeFor(statusCodes, successCodes, config);
    }

    return state;
  },
};
