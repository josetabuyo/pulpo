import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import { callLLM } from "./llm-client";

const LIST_NOISE_RE = /^\s*(?:[-*•]|\d+[.)])\s*/;
const WRAPPING_QUOTES_RE = /^["'“”](.*)["'“”]$/;

// TS port of _clean_list_line (pulpo/graphs/nodes/llm.py).
function cleanListLine(line: string): string {
  const cleaned = line.replace(LIST_NOISE_RE, "").trim();
  const m = WRAPPING_QUOTES_RE.exec(cleaned);
  return m ? m[1].trim() : cleaned;
}

// TS port of LLMNode (pulpo/graphs/nodes/llm.py). See lib/nodes/llm-client.ts
// for how the Python router (MODEL_ROUTER_URL, local-only) is replaced by a
// direct NVIDIA NIM → Groq → OpenRouter HTTP cascade. json_output is
// enforced via a prompt instruction instead of a provider-native
// response_format (Python's model_kwargs approach) -- response_format
// support isn't uniform across every provider in the cascade, so a soft
// prompt contract is the portable choice here.
export const llmNode: NodeDef = {
  label: "Respuesta LLM",
  color: "#6b21a8",
  description: "Genera una respuesta usando un modelo de lenguaje.",
  configSchema: {},
  async run(state, config) {
    if (state.fromDeltaSync) return state;

    const prompt = (config.prompt as string) ?? "";
    const model = (config.model as string) ?? "best:instruction|local-first";
    const temperature = Number(config.temperature ?? 0.3);
    const output = interpolate((config.output as string) ?? "reply", state);
    const jsonOut = Boolean(config.json_output);
    const replyKey = (config.json_reply_key as string) ?? "reply";
    const routeKey = (config.json_route_key as string) ?? "";
    const asList = Boolean(config.output_as_list);
    const maxTokens = (config.max_tokens as number | undefined) ?? undefined;

    let system = interpolate(prompt, state);
    if (jsonOut) {
      system += `\n\nRespondé ÚNICAMENTE con JSON válido, sin texto adicional. La clave "${replyKey}" debe contener el texto de la respuesta.`;
    }

    const { text, error } = await callLLM({
      systemPrompt: system,
      userMessage: state.message,
      model,
      temperature,
      maxTokens,
    });

    if (error) {
      state.data._llm_errors = [...((state.data._llm_errors as unknown[]) ?? []), { output, error }];
    }

    let finalText = text;
    if (jsonOut) {
      try {
        const parsed = JSON.parse(text);
        finalText = typeof parsed === "object" && parsed ? (parsed[replyKey] ?? "") : "";
        if (routeKey && typeof parsed === "object" && parsed?.[routeKey]) {
          state.data.route = String(parsed[routeKey]);
        }
      } catch {
        finalText = "";
      }
    }

    if (asList) {
      const items = finalText
        .split("\n")
        .filter((line) => line.trim())
        .map(cleanListLine)
        .filter((line) => line && !line.endsWith(":"))
        .map((line) => ({ text: line }));
      state.data[output] = items;
    } else {
      state.data[output] = finalText.trim();
    }

    return state;
  },
};
