// Prueba de viabilidad: generar un título corto y descriptivo para noticias
// de Luganense (`/api/noticias`, ver ADR-010) vía el cascade LLM que ya usa
// el nodo `llm` en producción (lib/nodes/llm-client.ts, categoría
// "summarization" -- NVIDIA/Groq/OpenRouter/Gemini, todos free-tier). La
// fuente hoy devuelve `title` = primera línea cruda del texto ("Nos llegó
// este mensaje", "Envía tu primer comentario...") -- inútil para listar.
//
// Uso: dotenv -e .env.local -- tsx scripts/generate-news-titles.ts [--count N]
import { getDb } from "../lib/db/client";
import { newsTitles } from "../lib/db/schema";
import { callLLM } from "../lib/nodes/llm-client";

const NOTICIAS_URL = "https://luganense.vercel.app/api/noticias?page_id=luganense&q=&offset=0&limit=";
const SOURCE = "luganense";

interface RawNoticia {
  id: string;
  title?: string;
  text?: string;
}

function parseCount(): number {
  const idx = process.argv.indexOf("--count");
  if (idx === -1) return 10;
  const n = Number(process.argv[idx + 1]);
  return Number.isFinite(n) && n > 0 ? n : 10;
}

async function fetchNoticias(count: number): Promise<RawNoticia[]> {
  const res = await fetch(`${NOTICIAS_URL}${count}`);
  if (!res.ok) throw new Error(`GET /api/noticias -> HTTP ${res.status}`);
  const data = (await res.json()) as { results?: RawNoticia[] };
  return data.results ?? [];
}

const SYSTEM_PROMPT =
  "Sos un editor de noticias de barrio. Te doy el texto crudo de una publicación " +
  "(a veces un aviso, un reclamo, un mensaje de vecino, un anuncio). Devolvé UN " +
  "título corto y descriptivo en español, de hasta 8 palabras, sin comillas ni " +
  "punto final, que resuma de qué trata. Nunca respondas con frases genéricas " +
  "como 'Nos llegó este mensaje' -- resumí el contenido real.";

async function main() {
  const count = parseCount();
  const noticias = await fetchNoticias(count);
  console.log(`Fetched ${noticias.length} noticias reales de Luganense.\n`);

  const db = getDb();
  const rows: { id: string; original: string; generated: string; ok: boolean; ms: number }[] = [];

  for (const n of noticias) {
    const text = (n.text ?? "").slice(0, 1500);
    const started = performance.now();
    const { text: generated, error } = await callLLM({
      systemPrompt: SYSTEM_PROMPT,
      userMessage: text,
      model: "best:summarization|cloud-first",
      temperature: 0.3,
      maxTokens: 40,
    });
    const ms = Math.round(performance.now() - started);
    const ok = !error && generated.trim().length > 0;
    const cleaned = generated.trim().replace(/^["']|["']$/g, "");

    rows.push({ id: n.id, original: (n.title ?? "").slice(0, 40), generated: ok ? cleaned : `<FALLÓ: ${error}>`, ok, ms });

    if (ok) {
      await db
        .insert(newsTitles)
        .values({
          id: crypto.randomUUID(),
          source: SOURCE,
          externalId: n.id,
          originalTitle: n.title ?? null,
          generatedTitle: cleaned,
        })
        .onConflictDoUpdate({
          target: [newsTitles.source, newsTitles.externalId],
          set: { generatedTitle: cleaned, originalTitle: n.title ?? null },
        });
    }
  }

  console.log("id".padEnd(4), "| original".padEnd(42), "| generado".padEnd(50), "| ms");
  console.log("-".repeat(110));
  for (const r of rows) {
    console.log(r.id.padEnd(4), "|", r.original.padEnd(40), "|", r.generated.padEnd(48), "|", r.ms);
  }

  const okCount = rows.filter((r) => r.ok).length;
  const avgMs = Math.round(rows.reduce((s, r) => s + r.ms, 0) / rows.length);
  console.log(`\n${okCount}/${rows.length} títulos generados OK. Latencia promedio: ${avgMs}ms.`);
  console.log("Costo: $0 -- todo el cascade (NVIDIA NIM / Groq / OpenRouter / Gemini) corre sobre modelos free-tier, sin billing por token configurado.");

  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
