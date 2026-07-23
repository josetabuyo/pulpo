import { desc, eq, gte } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flowRuns } from "@/lib/db/schema";

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

// Recent flow_runs, most recent first -- for drill-down under the chart
// (not consumed by the frontend yet, left ready per the handoff's pending
// "GET /api/runs para listar" item).
export async function listRuns(params: { status?: string; limit?: number }) {
  const db = getDb();
  const columns = {
    runId: flowRuns.runId,
    flowId: flowRuns.flowId,
    botId: flowRuns.botId,
    status: flowRuns.status,
    startedAt: flowRuns.startedAt,
    endedAt: flowRuns.endedAt,
    contactPhone: flowRuns.contactPhone,
  };
  const limit = params.limit ?? 20;

  if (params.status) {
    return db
      .select(columns)
      .from(flowRuns)
      .where(eq(flowRuns.status, params.status))
      .orderBy(desc(flowRuns.startedAt))
      .limit(limit);
  }
  return db.select(columns).from(flowRuns).orderBy(desc(flowRuns.startedAt)).limit(limit);
}
