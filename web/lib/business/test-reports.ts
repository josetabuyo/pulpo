import { desc, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { testReports } from "@/lib/db/schema";

// CRUD de reportes HTML de e2e (tab "Test" del bot card, 2026-07-24). Ver
// scripts/generate_e2e_report.py (Python, corre la suite y sube el
// resultado acá) -- esta capa solo lee/escribe la tabla, no genera nada.

type TestReportRow = typeof testReports.$inferSelect;

function toSummaryDto(row: Omit<TestReportRow, "html">) {
  return {
    id: row.id,
    bot_id: row.botId,
    slug: row.slug,
    title: row.title,
    created_at: row.createdAt,
  };
}

export async function listTestReports(botId: string) {
  const db = getDb();
  const rows = await db
    .select({
      id: testReports.id,
      botId: testReports.botId,
      slug: testReports.slug,
      title: testReports.title,
      createdAt: testReports.createdAt,
    })
    .from(testReports)
    .where(eq(testReports.botId, botId))
    .orderBy(desc(testReports.createdAt));
  return rows.map(toSummaryDto);
}

export async function getTestReportHtml(botId: string, reportId: string): Promise<string | null> {
  const db = getDb();
  const [row] = await db.select().from(testReports).where(eq(testReports.id, reportId));
  if (!row || row.botId !== botId) return null;
  return row.html;
}

// Alta -- upsert por `slug` (ver docstring de testReports en schema.ts:
// solo importa el ÚLTIMO reporte por flow). Llamado por un script one-off,
// no por una ruta HTTP -- no hay validación de auth acá, el caller ya corre
// con acceso directo a la DB (mismo patrón que scripts/add-chat-trigger-luganense.ts).
export async function upsertTestReport(input: { botId: string; slug: string; title: string; html: string }) {
  const db = getDb();
  await db
    .insert(testReports)
    .values({ id: crypto.randomUUID(), botId: input.botId, slug: input.slug, title: input.title, html: input.html })
    .onConflictDoUpdate({
      target: testReports.slug,
      set: { title: input.title, html: input.html, createdAt: new Date() },
    });
}
