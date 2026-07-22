import { start } from "workflow/api";
import { runFlowWorkflow } from "@/workflows/run-flow";
import { createFlowState } from "@/lib/nodes/state";

// TS port of POST /api/flows/{flow_id}/trigger/{node_id}
// (pulpo/interfaces/api/routers/flows.py), backed by ApiTriggerNode
// (pulpo/graphs/nodes/api_trigger.py). Unlike the Python version, this route
// requires auth (see proxy.ts) -- the spike closes that gap rather than
// reproducing it.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ flowId: string; nodeId: string }> }
) {
  const { flowId, nodeId } = await params;
  const body = await request.json().catch(() => ({}));

  const initialState = createFlowState({
    message: body.message ?? "",
    canal: "api",
    data: body.data ?? {},
  });

  const run = await start(runFlowWorkflow, [flowId, nodeId, initialState]);

  return Response.json({ run_id: run.runId });
}
