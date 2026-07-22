import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flowRuns, flowRunSteps } from "@/lib/db/schema";

// TS port of GET /runs/{run_id} (pulpo/interfaces/api/routers/runs.py) --
// enough to validate end-to-end in the spike (step 7 of the plan) that
// flow_runs/flow_run_steps get populated correctly by the Workflow DevKit
// executor, same journal shape the existing frontend "runs" panel expects.
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const db = getDb();

  const [run] = await db.select().from(flowRuns).where(eq(flowRuns.runId, runId));
  if (!run) return Response.json({ error: "run not found" }, { status: 404 });

  const steps = await db.select().from(flowRunSteps).where(eq(flowRunSteps.runId, runId));

  return Response.json({ ...run, steps });
}
