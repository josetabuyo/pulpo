import { asc, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flowRunSteps } from "@/lib/db/schema";
import { getRun } from "@/lib/business/run-stats";

// GET /runs/{run_id} -- detalle con steps, mismo contrato snake_case que el
// backend Python original (frontend/src/components/bot/RunsTab.jsx::RunDetail/
// StepRow leen step.node_id/node_type/branch_taken/input_state/output_state).
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;

  const run = await getRun(runId);
  if (!run) return Response.json({ error: "run not found" }, { status: 404 });

  const db = getDb();
  const stepRows = await db
    .select()
    .from(flowRunSteps)
    .where(eq(flowRunSteps.runId, runId))
    .orderBy(asc(flowRunSteps.id));

  const steps = stepRows.map((s) => ({
    id: s.id,
    node_id: s.nodeId,
    node_type: s.nodeType,
    started_at: s.startedAt,
    ended_at: s.endedAt,
    input_state: s.inputState,
    output_state: s.outputState,
    branch_taken: s.branchTaken,
    status: s.status,
    error_message: s.errorMessage,
  }));

  return Response.json({ ...run, steps });
}
