import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import { callVisionLLM } from "./llm-client";

// SIN el sandwich anti-prompt-injection que usa lib/nodes/llm.ts a propósito
// -- ahí tiene sentido porque separa instrucción (prompt del negocio) de
// dato no confiable ({{conversation}}, texto real del usuario final). Acá
// el `prompt` es contenido de autor del flow, no texto de un usuario final,
// así que envolverlo solo le agrega ruido al modelo. Probado con curl
// (2026-09-01): con el sandwich, el modelo de visión (NVIDIA
// llama-3.2-11b-vision-instruct) trataba el prompt entero como "dato a
// comentar" y devolvía un preámbulo conversacional + JSON envuelto en vez
// de JSON puro -- sin el sandwich, JSON limpio consistentemente.
const JSON_INSTRUCTION =
  "\n\nRespondé ÚNICAMENTE con un objeto JSON válido, sin texto antes ni después, " +
  "sin bloques de código markdown. La respuesta debe empezar con { y terminar con }. " +
  "Si no podés leer un dato con confianza, dejalo en null -- nunca inventes un valor.";

const EXT_MIME: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
};

export function guessMimeFromUrl(url: string): string {
  const match = /\.([a-z0-9]+)(?:\?|$)/i.exec(url);
  const ext = match?.[1]?.toLowerCase();
  return (ext && EXT_MIME[ext]) || "image/png";
}

async function fetchAsDataUri(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`no se pudo descargar la imagen (HTTP ${res.status})`);
  const contentType = res.headers.get("content-type")?.split(";")[0]?.trim();
  const mime = contentType && contentType.startsWith("image/") ? contentType : guessMimeFromUrl(url);
  const buf = Buffer.from(await res.arrayBuffer());
  return `data:${mime};base64,${buf.toString("base64")}`;
}

// Parsea la respuesta del modelo como JSON, tolerando el fence ```json que
// Gemini a veces agrega a pesar de la instrucción de "sin bloques de código".
export function parseJsonResponse(text: string): Record<string, unknown> {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text);
  const raw = (fenced ? fenced[1] : text).trim();
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
    return { _raw: text, _parse_error: true };
  } catch {
    return { _raw: text, _parse_error: true };
  }
}

// Lee un documento (imagen: factura, ticket) vía LLM con visión y guarda el
// JSON extraído en state.data[output]. Genérico a propósito -- qué campos
// extraer lo define el `prompt` de cada instancia del nodo en el flow, no
// está hardcodeado acá (ver management/PLAN_NODOS_PENDIENTES_MACH.md, pieza
// #2). Corre en Vercel Y local por igual -- descartado el OCR local de Wavi
// (Apple Vision, macOS-only) como camino principal, ver plan de esta sesión.
// Alcance v1: solo imagen, no PDF.
export const documentVisionNode: NodeDef = {
  label: "Lector de documentos (visión)",
  color: "#9333ea",
  description: "Manda una imagen a un modelo con visión y extrae datos estructurados en JSON.",
  configSchema: {},
  async run(state, config) {
    if (state.fromDeltaSync) return state;

    const prompt = (config.prompt as string) ?? "";
    const imageUrl = interpolate((config.image_url as string) ?? "{{attachment_url}}", state).trim();
    const output = interpolate((config.output as string) ?? "document_data", state);
    const temperature = Number(config.temperature ?? 0.1);
    const maxTokens = (config.max_tokens as number | undefined) ?? 500;

    // Sin adjunto en este mensaje -- no-op, sin llamar a ningún provider.
    // Permite que este nodo viva siempre en la cadena (trigger → vision →
    // llm → send) sin necesitar un condition node que ramifique.
    if (!imageUrl) {
      state.data[output] = null;
      return state;
    }

    const userText = interpolate(prompt, state) + JSON_INSTRUCTION;

    try {
      const imageDataUri = await fetchAsDataUri(imageUrl);
      const { text, error } = await callVisionLLM({ userText, imageDataUri, temperature, maxTokens });

      if (error) {
        state.data._llm_errors = [...((state.data._llm_errors as unknown[]) ?? []), { output, error }];
        state.data[output] = null;
        return state;
      }

      state.data[output] = parseJsonResponse(text);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      state.data._llm_errors = [...((state.data._llm_errors as unknown[]) ?? []), { output, error: message }];
      state.data[output] = null;
    }

    return state;
  },
};
