import { listRuns } from "@/lib/business/run-stats";

// GET /api/runs?status=&limit= -- recent flow_runs, most recent first.
// Complements /api/runs/stats and /api/runs/[runId] for drill-down; not
// consumed by the frontend yet (was the pending "GET /api/runs para
// listar" item from Fase 3 in the handoff).
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") ?? undefined;
  const limit = Number(searchParams.get("limit")) || undefined;
  const runs = await listRuns({ status, limit });
  return Response.json(runs);
}
