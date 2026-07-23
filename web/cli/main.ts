#!/usr/bin/env -S node
// Pulpo web CLI -- no-auth command-line access to `web/` for AI agents
// (management/HANDOFF_LOCAL_CLI_AND_NODES.md §4). Talks ONLY over HTTP to
// http://localhost:{WEB_BACKEND_PORT:-9010}/api/* -- never imports
// lib/business/* or touches the DB directly, on purpose: this way the CLI
// exercises the exact same code path as production (proxy -> route handler
// -> business -> DB), the no-auth bypass in proxy.ts/lib/auth/local-bypass.ts
// gets exercised for real on every use instead of only in theory, and the
// CLI can never drift from the API's actual contract.
//
// Requires PULPO_LOCAL_NO_AUTH=1 in web/.env.local (see
// lib/auth/local-bypass.ts) AND a `next dev` server actually running on
// WEB_BACKEND_PORT -- this is a client, it doesn't start anything. Output is
// always JSON on stdout (this is for agents, not humans -- no pretty
// tables); errors go to stderr with a non-zero exit code.
//
// This is NOT the Python CLI (`pulpo` / pulpo/interfaces/cli/main.ts) --
// that one talks to the SQLite/Python stack in-process and is untouched.
// This one only knows about `web/`.

import { readFileSync } from "node:fs";

const PORT = process.env.WEB_BACKEND_PORT ?? "9010";
const BASE_URL = process.env.PULPO_WEB_CLI_BASE_URL ?? `http://localhost:${PORT}`;

class CliError extends Error {}

function fail(message: string): never {
  console.error(JSON.stringify({ error: message }));
  process.exit(1);
}

// --- tiny arg parsing -- no framework, see handoff doc §4.2 ("un
// dispatcher a mano sobre process.argv alcanza para este tamaño").
// Positional args come first (in command order), then --flags (some
// boolean, some with a value).
interface ParsedArgs {
  positional: string[];
  flags: Record<string, string | boolean>;
}

function parseArgs(argv: string[]): ParsedArgs {
  const positional: string[] = [];
  const flags: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith("--")) {
      const key = arg.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith("--")) {
        flags[key] = next;
        i++;
      } else {
        flags[key] = true;
      }
    } else {
      positional.push(arg);
    }
  }
  return { positional, flags };
}

async function apiFetch(path: string, init?: RequestInit): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (err) {
    throw new CliError(
      `no se pudo conectar a ${BASE_URL}${path} -- ¿está corriendo \`npm run dev\` en web/? (${err instanceof Error ? err.message : String(err)})`,
    );
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    throw new CliError(`HTTP ${res.status} en ${path}: ${typeof body === "string" ? body : JSON.stringify(body)}`);
  }
  return body;
}

function readFileArg(flags: ParsedArgs["flags"]): unknown {
  const filePath = flags.file;
  if (typeof filePath !== "string") throw new CliError("falta --file <ruta a JSON del flow>");
  const raw = readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}

// /api/flows/{flowId}/trigger/{nodeId} deliberately stays on the JWT bearer
// scheme even for the local no-auth bypass -- see proxy.ts, TRIGGER_PATH_RE
// is checked BEFORE isLocalNoAuth() runs, and the handoff doc (§4.3) is
// explicit that the "esquemas... existentes" (public + bearer) stay intact,
// not folded into the new bypass block. That scheme was already built to
// not need a browser session (pulpo/graphs/nodes/api_trigger.py has no
// concept of one), so the CLI just uses it transparently: exchange
// ADMIN_PASSWORD (already in web/.env.local, loaded here via `dotenv -e`)
// for a short-lived JWT via the existing /api/auth/token route, same as a
// human would with curl. This is NOT a new bypass -- it's the CLI acting
// like any other bearer-token client of an endpoint that was already
// unauthenticated-by-session on purpose.
let cachedToken: string | null = null;

async function getBearerToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const password = process.env.ADMIN_PASSWORD;
  if (!password) {
    throw new CliError("ADMIN_PASSWORD no está seteada (necesaria para 'flows trigger' -- ver web/.env.local)");
  }
  const body = (await apiFetch("/api/auth/token", { method: "POST", body: JSON.stringify({ password }) })) as {
    access_token?: string;
  };
  if (!body.access_token) throw new CliError("no se pudo obtener un access_token de /api/auth/token");
  cachedToken = body.access_token;
  return cachedToken;
}

const TERMINAL_STATUSES = new Set(["completed", "waiting_gate", "error", "handed_off"]);

async function waitForRun(runId: string, { intervalMs = 1500, timeoutMs = 120_000 } = {}): Promise<unknown> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    // The workflow's flow_runs row can lag a beat behind start() returning
    // runId (Workflow DevKit persists it as the workflow's first async step
    // runs) -- a 404 right after triggering is "not created yet", not
    // "never will be", so keep polling instead of failing immediately.
    let run: { status?: string } | null = null;
    try {
      run = (await apiFetch(`/api/runs/${runId}`)) as { status?: string };
    } catch (err) {
      if (!(err instanceof CliError) || !err.message.includes("HTTP 404")) throw err;
    }
    if (run?.status && TERMINAL_STATUSES.has(run.status)) return run;
    if (Date.now() > deadline) {
      throw new CliError(`runs get ${runId} no llegó a un status terminal en ${timeoutMs}ms (último status: ${run?.status ?? "not found"})`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

async function main() {
  const [command, sub, ...rest] = process.argv.slice(2);
  if (!command) {
    fail(
      "uso: pulpo <bots|flows|runs|nodes> <subcomando> [args] -- ver management/HANDOFF_LOCAL_CLI_AND_NODES.md §4.2 para la tabla completa",
    );
  }

  const { positional, flags } = parseArgs(rest);
  let result: unknown;

  switch (`${command} ${sub}`) {
    case "bots list": {
      result = await apiFetch("/api/bots");
      break;
    }

    case "flows list": {
      const [botId] = positional;
      if (!botId) throw new CliError("uso: flows list <botId>");
      result = await apiFetch(`/api/flows/bots/${botId}`);
      break;
    }

    case "flows get": {
      const [botId, flowId] = positional;
      if (!botId || !flowId) throw new CliError("uso: flows get <botId> <flowId>");
      result = await apiFetch(`/api/flows/bots/${botId}/${flowId}`);
      break;
    }

    case "flows create": {
      const [botId] = positional;
      if (!botId) throw new CliError("uso: flows create <botId> --file flow.json");
      const body = readFileArg(flags);
      result = await apiFetch(`/api/flows/bots/${botId}`, { method: "POST", body: JSON.stringify(body) });
      break;
    }

    case "flows update": {
      const [botId, flowId] = positional;
      if (!botId || !flowId) throw new CliError("uso: flows update <botId> <flowId> --file flow.json");
      const body = readFileArg(flags);
      result = await apiFetch(`/api/flows/bots/${botId}/${flowId}`, { method: "PUT", body: JSON.stringify(body) });
      break;
    }

    case "flows delete": {
      const [botId, flowId] = positional;
      if (!botId || !flowId) throw new CliError("uso: flows delete <botId> <flowId>");
      result = await apiFetch(`/api/flows/bots/${botId}/${flowId}`, { method: "DELETE" });
      if (result === null) result = { ok: true };
      break;
    }

    case "flows trigger": {
      const [flowId, nodeId] = positional;
      if (!flowId || !nodeId) throw new CliError("uso: flows trigger <flowId> <nodeId> --message \"...\" [--contact ...] [--data '{...}'] [--wait]");
      const body: Record<string, unknown> = { message: flags.message ?? "" };
      if (typeof flags.contact === "string") body.contact_phone = flags.contact;
      if (typeof flags.data === "string") {
        try {
          body.data = JSON.parse(flags.data);
        } catch {
          throw new CliError("--data no es JSON válido");
        }
      }
      const token = await getBearerToken();
      const triggerResult = (await apiFetch(`/api/flows/${flowId}/trigger/${nodeId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })) as { run_id?: string };
      if (flags.wait && triggerResult.run_id) {
        result = await waitForRun(triggerResult.run_id);
      } else {
        result = triggerResult;
      }
      break;
    }

    case "runs list": {
      const params = new URLSearchParams();
      if (typeof flags.status === "string") params.set("status", flags.status);
      if (typeof flags.limit === "string") params.set("limit", flags.limit);
      const qs = params.toString();
      result = await apiFetch(`/api/runs${qs ? `?${qs}` : ""}`);
      break;
    }

    case "runs get": {
      const [runId] = positional;
      if (!runId) throw new CliError("uso: runs get <runId>");
      result = await apiFetch(`/api/runs/${runId}`);
      break;
    }

    case "nodes types": {
      result = await apiFetch("/api/flows/node-types");
      break;
    }

    default:
      throw new CliError(`comando desconocido: ${command} ${sub ?? ""}`.trim());
  }

  console.log(JSON.stringify(result, null, 2));
}

main().catch((err) => {
  if (err instanceof CliError) fail(err.message);
  fail(err instanceof Error ? err.message : String(err));
});
