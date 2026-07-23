// Replaces pulpo/graphs/nodes/llm.py's _build_llm() + MODEL_ROUTER_URL
// (local-models/router, localhost:9002 -- only reachable from the user's
// Mac). Also replaces the short-lived Vercel AI Gateway attempt (reverted
// 2026-07-22 -- AI Gateway requires a credit card on file before serving
// ANY request, even free-tier/BYOK, which blocked testing; see handoff doc).
//
// This calls NVIDIA NIM → Groq → OpenRouter directly over HTTP -- the same
// three providers and the same cascade order as local-models/router/
// dispatcher.py, just inlined here instead of proxied through that service
// (which only runs on the user's Mac). Plain OpenAI-compatible
// /chat/completions calls, no SDK, nothing Vercel-specific -- works from any
// Node runtime.
//
// Model picks per category mirror local-models/rankings/cloud.yaml's top
// entry per provider per category (as of 2026-07-22 -- re-sync by hand if
// that file changes; there's no automated link between the two repos).
//
// This file is the ONLY place that knows how an LLM call is actually
// dispatched. llm.ts and router.ts (the two node types that need an LLM)
// only call callLLM({systemPrompt, userMessage, model, temperature,
// maxTokens}) -> {text, error} -- they know nothing about providers, HTTP,
// or cascades. If local-models/router ever gets deployed as its own cloud
// service (see handoff doc), swapping to it is a change scoped entirely to
// this file: replace the cascade loop in callLLM() with a single fetch to
// that service's OpenAI-compatible endpoint. No caller changes.
//
// Local tier (2026-07-23, management/HANDOFF_LOCAL_CLI_AND_NODES.md §3.2,
// "Opción B"): re-enables the `|strategy` suffix of "best:category|strategy"
// that flows imported from Python already carry (llm.ts/router.ts's own
// default is literally "best:instruction|local-first"), instead of leaving
// it a dead string like before. Chosen over a separate `llm_local` node
// type because the config format already encodes this, this file is
// already the single despachador, and duplicating json_output/
// output_as_list/think-stripping into a second node type would break that
// pattern for no real gain (see handoff doc for the full pros/cons). Gated
// by isLocalDev() (lib/env.ts): on Vercel the local branch is never even
// evaluated, so behavior there is bit-for-bit identical to before this
// change -- the acceptance criterion from the handoff doc.
import { isLocalDev } from "@/lib/env";

export type Provider = "nvidia" | "groq" | "openrouter";

interface CascadeEntry {
  provider: Provider;
  model: string;
}

const PROVIDER_CONFIG: Record<Provider, { baseUrl: string; envKey: string }> = {
  nvidia: { baseUrl: "https://integrate.api.nvidia.com/v1", envKey: "NVIDIA_API_KEY" },
  groq: { baseUrl: "https://api.groq.com/openai/v1", envKey: "GROQ_API_KEY" },
  openrouter: { baseUrl: "https://openrouter.ai/api/v1", envKey: "OPENROUTER_API_KEY" },
};

// Some NVIDIA NIM models hang without explicit thinking=off (ported from
// local-models/router/dispatcher.py's _NVIDIA_THINKING_DEFAULTS).
const NVIDIA_THINKING_DEFAULTS: Record<string, Record<string, boolean>> = {
  "deepseek-ai/deepseek-v4-pro": { thinking: false },
  "deepseek-ai/deepseek-v4-flash": { thinking: false },
  "moonshotai/kimi-k2.6": { thinking: false },
  "qwen/qwen3.5-397b-a17b": { enable_thinking: false },
  "qwen/qwen3.5-122b-a10b": { enable_thinking: false },
};

const CATEGORY_CASCADE: Record<string, CascadeEntry[]> = {
  reasoning: [
    { provider: "nvidia", model: "deepseek-ai/deepseek-v4-pro" },
    { provider: "groq", model: "openai/gpt-oss-120b" },
    { provider: "openrouter", model: "google/gemma-4-31b-it:free" },
  ],
  coding: [
    { provider: "nvidia", model: "z-ai/glm-5.2" },
    { provider: "groq", model: "qwen/qwen3.6-27b" },
    { provider: "openrouter", model: "cohere/north-mini-code:free" },
  ],
  code_debug: [
    { provider: "nvidia", model: "z-ai/glm-5.2" },
    { provider: "groq", model: "qwen/qwen3.6-27b" },
    { provider: "openrouter", model: "cohere/north-mini-code:free" },
  ],
  math: [
    { provider: "nvidia", model: "deepseek-ai/deepseek-v4-pro" },
    { provider: "groq", model: "qwen/qwen3.6-27b" },
    { provider: "openrouter", model: "nvidia/nemotron-3-nano-30b-a3b:free" },
  ],
  summarization: [
    { provider: "nvidia", model: "moonshotai/kimi-k2.6" },
    { provider: "groq", model: "openai/gpt-oss-120b" },
    { provider: "openrouter", model: "google/gemma-4-31b-it:free" },
  ],
  instruction: [
    { provider: "nvidia", model: "qwen/qwen3.5-397b-a17b" },
    { provider: "groq", model: "llama-3.1-8b-instant" },
    { provider: "openrouter", model: "google/gemma-4-31b-it:free" },
  ],
  // Speed-first, same override as cloud.yaml: Groq LPU latency (2-8s) beats
  // NVIDIA's 397B model (40-60s) for conversational multilingual replies.
  multilingual: [
    { provider: "groq", model: "llama-3.1-8b-instant" },
    { provider: "nvidia", model: "qwen/qwen3.5-397b-a17b" },
    { provider: "openrouter", model: "google/gemma-4-31b-it:free" },
  ],
  context: [
    { provider: "nvidia", model: "z-ai/glm-5.2" },
    { provider: "groq", model: "openai/gpt-oss-120b" },
    { provider: "openrouter", model: "nvidia/nemotron-3-ultra-550b-a55b:free" },
  ],
};

const DEFAULT_CASCADE = CATEGORY_CASCADE.instruction;

// TS port of parse_model_strategy (pulpo/graphs/nodes/llm.py) -- resolves to
// a provider cascade instead of a (model, router_strategy) tuple. The
// `strategy` half of "best:category|strategy" is used only to pick the
// cloud cascade's category; whether/how the local tier gets a shot lives in
// resolveLocalStrategy() below.
export function resolveCascade(raw: string): CascadeEntry[] {
  if (raw.startsWith("best:")) {
    const category = raw.slice("best:".length).split("|")[0];
    return CATEGORY_CASCADE[category] ?? DEFAULT_CASCADE;
  }
  // Legacy literal prefixes from the Python side (ollama/*, groq/*, local:*)
  // don't apply here -- fall back to the default cascade rather than guess.
  return DEFAULT_CASCADE;
}

type LocalStrategy = "local" | "local-first" | "cloud-first" | "cloud";

interface ParsedModel {
  category: string;
  strategy: LocalStrategy;
}

// TS port of parse_model_strategy's alias half (pulpo/graphs/nodes/llm.py) --
// same default as Python: no "|suffix" at all defaults to "local-first",
// not "cloud" (matches llm.ts/router.ts's own default config value).
function parseModel(raw: string): ParsedModel | null {
  if (!raw.startsWith("best:")) return null;
  const rest = raw.slice("best:".length);
  const [category, alias] = rest.split("|");
  const strategy: LocalStrategy =
    alias === "local" || alias === "local-first" || alias === "cloud-first" || alias === "cloud" ? alias : "local-first";
  return { category, strategy };
}

const ROUTER_URL = process.env.MODEL_ROUTER_URL ?? "http://localhost:9002";

// Cheap pre-check so a router that isn't running fails in ~2s instead of
// waiting out the real completion's long timeout (per the handoff doc --
// local Ollama models can take >60s to respond for real).
async function routerIsUp(): Promise<boolean> {
  try {
    const res = await fetch(`${ROUTER_URL}/health`, { signal: AbortSignal.timeout(2_000) });
    return res.ok;
  } catch {
    return false;
  }
}

// Mirrors _build_llm()'s endpoint-per-strategy mapping (pulpo/graphs/nodes/
// llm.py ~L128-183), simplified to the two paths that matter here:
//   - "local"       → {ROUTER}/local/v1, no fallback if it fails (matches
//                      Python's local-only: no with_fallbacks() call there).
//   - "local-first"  → {ROUTER}/v1 hybrid endpoint with the
//                      X-Router-Strategy header, same as Python.
// "cloud-first"/"cloud" deliberately do NOT attempt the local tier here --
// simplification documented in the handoff (§3.2): the direct 3-provider
// cloud cascade below already gives more redundancy than the Python
// router's single "cloud" tier + one local fallback, so there's little
// value in also routing those two through the local router first. `cloud`
// still gets a local-as-last-resort attempt in callLLM() below if the
// entire cloud cascade fails, mirroring "cloud-best-with-local-fallback".
async function callLocalRouter(
  strategy: "local" | "local-first",
  category: string,
  opts: { systemPrompt: string; userMessage: string; temperature: number; maxTokens?: number },
): Promise<string> {
  const path = strategy === "local" ? "/local/v1/chat/completions" : "/v1/chat/completions";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (strategy === "local-first") headers["X-Router-Strategy"] = "local-first";

  const body: Record<string, unknown> = {
    // local-models/router resolves "best:category" itself against its own
    // rankings (same string Python passed through as `model=model` in
    // _build_llm()) -- no API key needed, the router doesn't require one.
    model: `best:${category}`,
    messages: [
      { role: "system", content: opts.systemPrompt },
      { role: "user", content: opts.userMessage },
    ],
    temperature: opts.temperature,
  };
  if (opts.maxTokens) body.max_tokens = opts.maxTokens;

  const res = await fetch(`${ROUTER_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    // Real local/Ollama completions can run long -- generous timeout, this
    // only runs after routerIsUp()'s cheap pre-check already passed.
    signal: AbortSignal.timeout(90_000),
  });
  if (!res.ok) {
    throw new Error(`local-models router ${path} → HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }
  const data = (await res.json()) as ChatCompletionResponse;
  return data.choices?.[0]?.message?.content ?? "";
}

interface ChatCompletionResponse {
  choices?: Array<{ message?: { content?: string } }>;
}

async function callProvider(
  entry: CascadeEntry,
  opts: { systemPrompt: string; userMessage: string; temperature: number; maxTokens?: number },
): Promise<string> {
  const { baseUrl, envKey } = PROVIDER_CONFIG[entry.provider];
  const apiKey = process.env[envKey];
  if (!apiKey) throw new Error(`${envKey} no está seteada`);

  const body: Record<string, unknown> = {
    model: entry.model,
    messages: [
      { role: "system", content: opts.systemPrompt },
      { role: "user", content: opts.userMessage },
    ],
    temperature: opts.temperature,
  };
  if (opts.maxTokens) body.max_tokens = opts.maxTokens;
  if (entry.provider === "nvidia" && NVIDIA_THINKING_DEFAULTS[entry.model]) {
    body.chat_template_kwargs = NVIDIA_THINKING_DEFAULTS[entry.model];
  }

  const res = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
      "User-Agent": "pulpo-web/1.0",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${entry.provider}/${entry.model} → HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }
  const data = (await res.json()) as ChatCompletionResponse;
  return data.choices?.[0]?.message?.content ?? "";
}

const THINK_BLOCK_RE = /<think>[\s\S]*?<\/think>/gi;

// TS port of _strip_think_blocks (pulpo/graphs/nodes/llm.py) -- see that
// module's docstring for the real bug this guards against (reasoning models
// leaking chain-of-thought into `content` instead of a separate field).
function stripThinkBlocks(content: string): string {
  return content.replace(THINK_BLOCK_RE, "").trim();
}

export interface LLMCallResult {
  text: string;
  error: string | null;
}

// TS port of the LLM-invocation core shared by LLMNode and RouterNode
// (pulpo/graphs/nodes/llm.py's inline call in .run(), pulpo/graphs/nodes/router.py).
// Tries each provider in the category's cascade in order -- unlike the
// Python side (which retries the SAME model once on empty content, then
// gives up), this also falls through to the NEXT provider on error or empty
// content, matching the 3-provider redundancy the user's own router gave.
export async function callLLM(opts: {
  systemPrompt: string;
  userMessage: string;
  model: string;
  temperature: number;
  maxTokens?: number;
}): Promise<LLMCallResult> {
  const errors: string[] = [];
  const parsed = parseModel(opts.model);

  // Local tier -- only even considered in local dev (see lib/env.ts's
  // header comment for why this file gates on isLocalDev() itself rather
  // than trusting a caller to check first).
  if (parsed && isLocalDev() && (parsed.strategy === "local" || parsed.strategy === "local-first")) {
    if (await routerIsUp()) {
      try {
        const raw = await callLocalRouter(parsed.strategy, parsed.category, opts);
        const text = stripThinkBlocks(raw);
        if (text) return { text, error: null };
        errors.push(`local-models(${parsed.strategy}): contenido vacío`);
      } catch (err) {
        errors.push(`local-models(${parsed.strategy}): ${err instanceof Error ? err.message : String(err)}`);
      }
    } else {
      errors.push(`local-models router no responde en ${ROUTER_URL} (GET /health)`);
    }

    if (parsed.strategy === "local") {
      // Strict "local-only" -- no fallback, same as Python's local-only
      // branch (_build_llm() never wraps it in with_fallbacks()).
      return { text: "", error: `Estrategia "local" falló sin fallback — ${errors.join(" | ")}` };
    }
    // "local-first" falls through to the cloud cascade below on failure --
    // that IS the "first" semantics.
  }

  const cascade = resolveCascade(opts.model);

  for (const entry of cascade) {
    try {
      const raw = await callProvider(entry, opts);
      const text = stripThinkBlocks(raw);
      if (text) return { text, error: null };
      errors.push(`${entry.provider}/${entry.model}: contenido vacío`);
    } catch (err) {
      errors.push(`${entry.provider}/${entry.model}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // Last-resort local fallback for the explicit "cloud" strategy when the
  // whole cloud cascade failed AND we're in local dev -- mirrors Python's
  // "cloud-best-with-local-fallback" (_build_llm()'s `cloud` branch wraps
  // the cloud client in `.with_fallbacks([local_fallback])`).
  if (parsed && parsed.strategy === "cloud" && isLocalDev() && (await routerIsUp())) {
    try {
      const raw = await callLocalRouter("local", parsed.category, opts);
      const text = stripThinkBlocks(raw);
      if (text) return { text, error: null };
      errors.push("local-models(cloud-fallback): contenido vacío");
    } catch (err) {
      errors.push(`local-models(cloud-fallback): ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return { text: "", error: `Toda la cascada falló — ${errors.join(" | ")}` };
}
