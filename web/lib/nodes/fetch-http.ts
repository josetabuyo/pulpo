import type { NodeDef } from "./base";
import type { FlowState } from "./state";
import { interpolate } from "./interpolate";

// TS port of FetchHttpNode (pulpo/graphs/nodes/fetch_http.py), scoped down
// for the spike: GET/POST, extract text/json/html, output key, url + body
// interpolation, {{query}}/{{message}} fallback. Deliberately out of scope
// (not needed to validate the Workflow DevKit fit, can be ported later):
// array_input (per-item fan-out), extract_fields (JSON path extraction),
// route_output (HTTP-status-based routing).

function recordFetchError(state: FlowState, url: string, error: string, statusCode?: number) {
  const errors = (state.data._fetch_errors as unknown[]) ?? [];
  errors.push({ url, status_code: statusCode ?? null, error });
  state.data._fetch_errors = errors;
}

function interpolateDeep(value: unknown, state: FlowState): unknown {
  if (typeof value === "string") return interpolate(value, state);
  if (Array.isArray(value)) return value.map((v) => interpolateDeep(v, state));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, interpolateDeep(v, state)])
    );
  }
  return value;
}

function resolveUrl(urlTemplate: string, state: FlowState): string {
  const queryValue =
    (state.data.query as string | undefined) ||
    (state.data.necesidad as string | undefined) ||
    state.message ||
    "";
  let url = urlTemplate
    .replaceAll("{{query}}", encodeURIComponent(queryValue))
    .replaceAll("{{message}}", encodeURIComponent(state.message || ""))
    .replaceAll("{query}", encodeURIComponent(queryValue))
    .replaceAll("{message}", encodeURIComponent(state.message || ""));
  return interpolate(url, state);
}

const UNRESOLVED_TEMPLATE_RE = /\{\{.*?\}\}/;

export const fetchHttpNode: NodeDef = {
  label: "Fetch HTTP",
  color: "#1e40af",
  description: "Hace un llamado HTTP (GET o POST) a una URL externa y guarda la respuesta como contexto.",
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

    if (!urlTemplate) return state;

    const url = resolveUrl(urlTemplate, state);

    if (UNRESOLVED_TEMPLATE_RE.test(url)) {
      recordFetchError(state, url, "unresolved {{...}} placeholder in URL");
      return state;
    }

    try {
      const body = method === "POST" ? interpolateDeep(config.body ?? {}, state) : undefined;
      const res = await fetch(url, {
        method,
        headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
        body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
      });

      if (!res.ok) {
        recordFetchError(state, url, `HTTP ${res.status}`, res.status);
        return state;
      }

      if (extract === "json" || extract === "html") {
        state.data[output] = await res.text();
      } else {
        const raw = await res.text();
        const text = raw.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        state.data[output] = text.slice(0, 5000);
      }
    } catch (err) {
      recordFetchError(state, url, err instanceof Error ? err.message : String(err));
    }

    return state;
  },
};
