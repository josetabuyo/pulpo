import { and, desc, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { publishedTestReports } from "@/lib/db/schema";
import { getEnvironment } from "@/lib/business/environments";
import { getTestRunsBySuiteRunId, getLatestSuiteRunId } from "@/lib/business/test-cases";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// "Publicar" en la tab "Test" -- push de una corrida (suite_run_id) hacia
// otro ambiente Pulpo conocido, mismo patrón de seguridad que
// lib/business/environment-sync.ts: el admin_token del ambiente remoto nunca
// sale de este proceso, el browser solo habla con /api/environments/{name}/
// test-reports de ESTE backend. A diferencia del sync de flows (pull/push,
// bidireccional), publicar un reporte es SIEMPRE push -- no existe "traer"
// un reporte de otro ambiente.
//
// El reporte publicado es un snapshot self-contained (jsonb `runs`, ver
// lib/db/schema.ts::publishedTestReports) -- necesario porque puede llegar
// desde OTRO ambiente Pulpo, donde los test_runs.id originales ni siquiera
// existen. Se guarda en su PROPIA tabla, separada de test_runs (que la
// política de retención va comprimiendo/borrando con el tiempo, ver
// enforceRunRetention) -- así un reporte publicado sobrevive aunque la
// corrida original ya se haya purgado.

function toDto(row: typeof publishedTestReports.$inferSelect) {
  return {
    id: row.id,
    bot_id: row.botId,
    suite_run_id: row.suiteRunId,
    summary: row.summary,
    runs: row.runs,
    published_at: row.publishedAt,
  };
}

export function buildSummary(runs: { status: string }[]) {
  return {
    total: runs.length,
    passed: runs.filter((r) => r.status === "passed").length,
    failed: runs.filter((r) => r.status !== "passed").length,
  };
}

// ─── Lado que RECIBE (local, expuesto vía sync-token a otro ambiente, y a
// esta misma instancia cuando publica "hacia sí misma" en dev) ────────────

export async function upsertPublishedReport(
  botId: string,
  reportId: string,
  payload: { suite_run_id: string; runs: unknown[]; published_at: string },
) {
  if (!Array.isArray(payload.runs) || !payload.runs.length) {
    throw new ValidationError("runs no puede estar vacío");
  }
  const db = getDb();
  const summary = buildSummary(payload.runs as { status: string }[]);
  const row = {
    id: reportId,
    botId,
    suiteRunId: payload.suite_run_id,
    summary,
    runs: payload.runs,
    publishedAt: new Date(payload.published_at),
  };
  await db
    .insert(publishedTestReports)
    .values(row)
    .onConflictDoUpdate({ target: publishedTestReports.id, set: row });
  return {
    id: row.id,
    bot_id: row.botId,
    suite_run_id: row.suiteRunId,
    summary: row.summary,
    runs: row.runs,
    published_at: row.publishedAt,
  };
}

export async function listPublishedReports(botId: string) {
  const db = getDb();
  const rows = await db
    .select()
    .from(publishedTestReports)
    .where(eq(publishedTestReports.botId, botId))
    .orderBy(desc(publishedTestReports.publishedAt));
  return rows.map(toDto);
}

export async function getPublishedReport(botId: string, reportId: string) {
  const db = getDb();
  const [row] = await db
    .select()
    .from(publishedTestReports)
    .where(and(eq(publishedTestReports.id, reportId), eq(publishedTestReports.botId, botId)));
  if (!row) throw new NotFoundError(`Reporte no encontrado: ${reportId}`);
  return toDto(row);
}

// ─── Lado que PUBLICA (local, botón "Publicar") ───────────────────────────

// La vista pública (EmbedTestReportsPage.jsx) solo muestra turnos +
// resultados de checks -- `steps`/`flow_snapshot` son el journal completo
// del compiler (cientos de KB por corrida, pensado para el gemelo
// interactivo de la tab "Test", que acá no existe) y `diagram_image` es un
// PNG base64 (~500KB). Publicar el detalle completo de una suite de 10
// casos supera fácil los ~4.5MB de body que Vercel acepta por request (413
// real, visto en pruebas) sin agregar nada que la vista pública use --
// recortar acá, no en el storage local de test_runs.
function toPublicRunPayload(run: Awaited<ReturnType<typeof getTestRunsBySuiteRunId>>[number]) {
  return {
    id: run.id,
    bot_id: run.bot_id,
    suite_run_id: run.suite_run_id,
    test_case_id: run.test_case_id,
    test_case_title: run.test_case_title,
    target: run.target,
    status: run.status,
    turns: run.turns,
    check_results: run.check_results,
    error_message: run.error_message,
    started_at: run.started_at,
    finished_at: run.finished_at,
  };
}

export async function publishSuiteRunToEnvironment(envName: string, botId: string, suiteRunId?: string) {
  const resolvedSuiteRunId = suiteRunId || (await getLatestSuiteRunId(botId));
  if (!resolvedSuiteRunId) throw new NotFoundError(`El bot ${botId} todavía no tiene corridas de test`);

  const fullRuns = await getTestRunsBySuiteRunId(botId, resolvedSuiteRunId);
  if (!fullRuns.length) throw new NotFoundError(`No hay resultados para la corrida ${resolvedSuiteRunId}`);
  const runs = fullRuns.map(toPublicRunPayload);

  const env = await getEnvironment(envName);
  const reportId = crypto.randomUUID();
  const publishedAt = new Date().toISOString();
  const payload = { suite_run_id: resolvedSuiteRunId, runs, published_at: publishedAt };

  let res: Response;
  try {
    res = await fetch(`${env.base_url}/api/test-reports/bots/${botId}/${reportId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Pulpo-Sync-Token": env.admin_token },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    throw new ValidationError(`No se pudo conectar a ${env.base_url}: ${err instanceof Error ? err.message : String(err)}`);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ValidationError(
      `El ambiente remoto respondió ${res.status}: ${body && typeof body === "object" && "detail" in body ? body.detail : JSON.stringify(body)}`,
    );
  }
  return { environment: envName, report_id: reportId, suite_run_id: resolvedSuiteRunId, summary: buildSummary(runs as { status: string }[]) };
}
