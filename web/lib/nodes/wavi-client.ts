import { isLocalDev } from "@/lib/env";

// The ONLY file that knows how to talk to Wavi's standalone HTTP server
// (see management/HANDOFF_LOCAL_CLI_AND_NODES.md §3.1) -- same SOLID
// pattern as llm-client.ts / lib/business/telegram.ts's sendTelegramMessage.
// Wavi (/Users/josetabuyo/Development/wavi) is a separate project/LAS agent
// that automates WhatsApp Web via a real, logged-in Chromium session. It is
// NOT reimplemented here, NOT imported as Python-in-Node -- this is a thin
// HTTP client against its FastAPI server (default port 8900, that's WAVI's
// own default, not a port we own or claim).
//
// The isLocalDev() gate and the fetch timeout both live HERE, not in the
// node defs (wavi.ts) -- any future node that wants to talk to Wavi
// inherits the "never touches the network in production" protection for
// free, and never throws: every function returns {ok, data?, error?}.
const BASE_URL = process.env.WAVI_SERVER_URL ?? "http://localhost:8900";

export interface WaviResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

async function call<T>(path: string, init: RequestInit, timeoutMs: number): Promise<WaviResult<T>> {
  if (!isLocalDev()) {
    // Structurally unreachable in production/Vercel -- see lib/env.ts. No
    // fetch is even attempted, so there's no risk of a hung connection or
    // an accidental request out of a serverless function.
    return { ok: false, error: "wavi solo disponible en dev local" };
  }
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) {
      return { ok: false, error: `wavi ${path} → HTTP ${res.status}: ${(await res.text()).slice(0, 300)}` };
    }
    const data = (await res.json()) as T;
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: `wavi ${path} no respondió: ${err instanceof Error ? err.message : String(err)}` };
  }
}

export interface WaviHealth {
  status: string;
  version?: string;
}

export function waviHealth(): Promise<WaviResult<WaviHealth>> {
  return call<WaviHealth>("/health", { method: "GET" }, 2_000);
}

export interface WaviStatus {
  session: string;
  daemon: boolean;
  authenticated: boolean;
}

export function waviStatus(session: string): Promise<WaviResult<WaviStatus>> {
  return call<WaviStatus>(`/status/${encodeURIComponent(session)}`, { method: "GET" }, 2_000);
}

export interface WaviSendResult {
  ok: boolean;
  contact: string;
  input_coords?: unknown;
}

export function waviSend(opts: { session: string; contact: string; message: string }): Promise<WaviResult<WaviSendResult>> {
  // Generous timeout: sending through a real WhatsApp Web session (typing +
  // clicking coordinates in Chromium) is slower than a plain API call.
  return call<WaviSendResult>("/send", { method: "POST", body: JSON.stringify(opts) }, 30_000);
}

export interface WaviBubble {
  [key: string]: unknown;
}

export interface WaviGetResult {
  contact: string;
  session: string;
  count: number;
  bubbles: WaviBubble[];
}

export function waviGet(opts: {
  session: string;
  contact: string;
  assets_dir?: string;
  from_date?: string;
  newest?: number;
  grow?: boolean;
  max_iter?: number;
}): Promise<WaviResult<WaviGetResult>> {
  // /get can take tens of seconds when `grow` is set (per the handoff doc) --
  // much longer than /health's cheap pre-check.
  return call<WaviGetResult>("/get", { method: "POST", body: JSON.stringify(opts) }, 60_000);
}
