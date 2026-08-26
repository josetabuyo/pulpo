// Genera un título corto y descriptivo para noticias de Luganense
// (`/api/noticias`, ver ADR-010) vía el cascade LLM que ya usa el nodo `llm`
// en producción (lib/nodes/llm-client.ts, categoría "summarization" --
// NVIDIA/Groq/OpenRouter/Gemini, todos free-tier). La fuente hoy devuelve
// `title` = primera línea cruda del texto ("Nos llegó este mensaje", "Envía
// tu primer comentario...") -- inútil para listar.
//
// Cachea en news_titles keyed por (source, external_id) -- por default salta
// los ids que ya tienen fila (no vuelve a gastar una llamada LLM por algo ya
// generado). --regenerate fuerza recalcular todo el batch igual.
//
// Uso:
//   dotenv -e .env.local -- tsx scripts/generate-news-titles.ts             # todas las pendientes
//   dotenv -e .env.local -- tsx scripts/generate-news-titles.ts --count 10  # limita el batch
//   dotenv -e .env.local -- tsx scripts/generate-news-titles.ts --regenerate # ignora el cache
import { and, eq, inArray } from "drizzle-orm";
import { getDb } from "../lib/db/client";
import { newsTitles } from "../lib/db/schema";
import { callLLM } from "../lib/nodes/llm-client";

const NOTICIAS_URL = "https://luganense.vercel.app/api/noticias?page_id=luganense&q=&offset=0&limit=";
const SOURCE = "luganense";
const FETCH_LIMIT_CAP = 1000; // techo defensivo -- el endpoint hoy no pagina de verdad

interface RawNoticia {
  id: string;
  title?: string;
  text?: string;
}

function parseArgs(): { count?: number; regenerate: boolean } {
  const idx = process.argv.indexOf("--count");
  const count = idx === -1 ? undefined : Number(process.argv[idx + 1]);
  return {
    count: Number.isFinite(count) && (count as number) > 0 ? count : undefined,
    regenerate: process.argv.includes("--regenerate"),
  };
}

async function fetchNoticias(limit: number): Promise<{ results: RawNoticia[]; total: number }> {
  const res = await fetch(`${NOTICIAS_URL}${limit}`);
  if (!res.ok) throw new Error(`GET /api/noticias -> HTTP ${res.status}`);
  const data = (await res.json()) as { results?: RawNoticia[]; total?: number };
  return { results: data.results ?? [], total: data.total ?? (data.results ?? []).length };
}

async function fetchAlreadyCachedIds(db: ReturnType<typeof getDb>, ids: string[]): Promise<Set<string>> {
  if (ids.length === 0) return new Set();
  const rows = await db
    .select({ externalId: newsTitles.externalId })
    .from(newsTitles)
    .where(and(eq(newsTitles.source, SOURCE), inArray(newsTitles.externalId, ids)));
  return new Set(rows.map((r) => r.externalId));
}

const SYSTEM_PROMPT =
  "Sos un editor de noticias de barrio. Te doy el texto crudo de una publicación " +
  "(a veces un aviso, un reclamo, un mensaje de vecino, un anuncio). Devolvé UN " +
  "título corto y descriptivo en español, de hasta 8 palabras, sin comillas ni " +
  "punto final, que resuma de qué trata. Nunca respondas con frases genéricas " +
  "como 'Nos llegó este mensaje' -- resumí el contenido real.";

async function main() {
  const { count, regenerate } = parseArgs();

  const { results: all, total } = await fetchNoticias(count ?? FETCH_LIMIT_CAP);
  console.log(`Fuente: ${all.length}/${total} noticias.`);

  const db = getDb();
  const cached = regenerate ? new Set<string>() : await fetchAlreadyCachedIds(db, all.map((n) => n.id));
  const pending = all.filter((n) => !cached.has(n.id));

  console.log(
    regenerate
      ? `--regenerate: se van a re-generar las ${pending.length} noticias del batch.`
      : `${cached.size} ya tenían título en cache, se saltean. Pendientes: ${pending.length}.\n`,
  );

  if (pending.length === 0) {
    console.log("Nada para hacer.");
    process.exit(0);
  }

  const rows: { id: string; original: string; generated: string; ok: boolean; ms: number }[] = [];

  for (const n of pending) {
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
  console.log(`\n${okCount}/${rows.length} títulos generados OK (${cached.size} saltados por cache). Latencia promedio: ${avgMs}ms.`);
  console.log("Costo: $0 -- todo el cascade (NVIDIA NIM / Groq / OpenRouter / Gemini) corre sobre modelos free-tier, sin billing por token configurado.");

  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
