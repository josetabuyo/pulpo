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
// `strategy` half of "best:category|strategy" (local-first, cloud-first,
// etc.) is ignored: there's no local/Ollama tier reachable from Vercel, so
// every strategy just runs the same NIM→Groq→OpenRouter cloud cascade.
export function resolveCascade(raw: string): CascadeEntry[] {
  if (raw.startsWith("best:")) {
    const category = raw.slice("best:".length).split("|")[0];
    return CATEGORY_CASCADE[category] ?? DEFAULT_CASCADE;
  }
  // Legacy literal prefixes from the Python side (ollama/*, groq/*, local:*)
  // don't apply here -- fall back to the default cascade rather than guess.
  return DEFAULT_CASCADE;
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
  const cascade = resolveCascade(opts.model);
  const errors: string[] = [];

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

  return { text: "", error: `Toda la cascada falló — ${errors.join(" | ")}` };
}
