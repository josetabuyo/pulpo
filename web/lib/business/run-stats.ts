import { and, desc, eq, gte } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flowRuns, flows } from "@/lib/db/schema";

// Bucketed success/error/pending counts of flow_runs for the Monitor panel's
// overlapping chart (frontend/src/components/MonitorPanel.jsx). This is
// business-level activity (flow triggers), not Vercel's HTTP-request
// runtime logs -- those already have their own native levels/histogram in
// the Vercel dashboard, see management/HANDOFF_VERCEL_DEEP_MIGRATION.md.
//
// success = completed | handed_off (both are normal terminations --
// handed_off is a wait_user/gate run passing the baton to a new run, not a
// failure). error = status === "error". pending = running | waiting_gate.
export interface RunStatsBucket {
  startedAt: string;
  success: number;
  error: number;
  pending: number;
}

export async function getRunStats(params: {
  since: Date;
  bucketMinutes: number;
}): Promise<{ bucketMinutes: number; buckets: RunStatsBucket[] }> {
  const db = getDb();
  const rows = await db
    .select({ startedAt: flowRuns.startedAt, status: flowRuns.status })
    .from(flowRuns)
    .where(gte(flowRuns.startedAt, params.since));

  const bucketMs = params.bucketMinutes * 60 * 1000;
  const sinceMs = params.since.getTime();
  const nowMs = Date.now();
  const bucketCount = Math.max(1, Math.ceil((nowMs - sinceMs) / bucketMs));

  const buckets: RunStatsBucket[] = Array.from({ length: bucketCount }, (_, i) => ({
    startedAt: new Date(sinceMs + i * bucketMs).toISOString(),
    success: 0,
    error: 0,
    pending: 0,
  }));

  for (const row of rows) {
    if (!row.startedAt) continue;
    const t = new Date(row.startedAt).getTime();
    const idx = Math.floor((t - sinceMs) / bucketMs);
    if (idx < 0 || idx >= bucketCount) continue;
    if (row.status === "completed" || row.status === "handed_off") buckets[idx].success++;
    else if (row.status === "error") buckets[idx].error++;
    else buckets[idx].pending++; // running | waiting_gate
  }

  return { bucketMinutes: params.bucketMinutes, buckets };
}

// DTO snake_case -- RunsTab.jsx/RunDetail (frontend/src/components/bot/RunsTab.jsx)
// leen run.run_id/flow_id/started_at/ended_at/is_sim/trigger_data, mismo
// contrato que el backend Python original. listRuns()/getRun() antes
// devolvían las filas de Drizzle tal cual (camelCase) -- nunca las consumía
// nadie hasta ahora (2026-07-24, primer e2e real), por eso no se notó.
// flow_name viene de un LEFT JOIN con flows -- null si el flow fue borrado
// (la tab Ejecuciones ya sabe mostrar el flow_id como fallback en ese caso).
function toRunDto(row: typeof flowRuns.$inferSelect, flowName: string | null) {
  return {
    run_id: row.runId,
    flow_id: row.flowId,
    flow_name: flowName,
    bot_id: row.botId,
    connection_id: row.connectionId,
    status: row.status,
    started_at: row.startedAt,
    ended_at: row.endedAt,
    trigger_data: row.triggerData,
    contact_phone: row.contactPhone,
    resume_node_id: row.resumeNodeId,
    is_sim: row.isSim,
  };
}

// Recent flow_runs, most recent first -- para el drill-down de la tab
// Ejecuciones. `botId` filtra a los runs de un bot puntual (RunsTab.jsx
// pega a /api/runs/bots/{botId}); sin botId es el listado global (Monitor).
export async function listRuns(params: { botId?: string; status?: string; limit?: number }) {
  const db = getDb();
  const limit = params.limit ?? 20;
  const conditions = [];
  if (params.botId) conditions.push(eq(flowRuns.botId, params.botId));
  if (params.status) conditions.push(eq(flowRuns.status, params.status));

  const rows = await db
    .select({ run: flowRuns, flowName: flows.name })
    .from(flowRuns)
    .leftJoin(flows, eq(flows.id, flowRuns.flowId))
    .where(conditions.length ? and(...conditions) : undefined)
    .orderBy(desc(flowRuns.startedAt))
    .limit(limit);
  return rows.map((r) => toRunDto(r.run, r.flowName));
}

export async function getRun(runId: string) {
  const db = getDb();
  const [row] = await db
    .select({ run: flowRuns, flowName: flows.name })
    .from(flowRuns)
    .leftJoin(flows, eq(flows.id, flowRuns.flowId))
    .where(eq(flowRuns.runId, runId));
  return row ? toRunDto(row.run, row.flowName) : null;
}
