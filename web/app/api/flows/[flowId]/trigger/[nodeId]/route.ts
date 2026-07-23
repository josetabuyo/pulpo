import { eq } from "drizzle-orm";
import { start } from "workflow/api";
import { runFlowWorkflow } from "@/workflows/run-flow";
import { createFlowState } from "@/lib/nodes/state";
import { getDb } from "@/lib/db/client";
import { flows } from "@/lib/db/schema";
import { continueConversation } from "@/lib/flow/conversation";
import { endFlowRunHandedOff, getWaitingGateRun, restoreSlotsForResume } from "@/lib/business/telegram";

// TS port of POST /api/flows/{flow_id}/trigger/{node_id}
// (pulpo/interfaces/api/routers/flows.py), backed by ApiTriggerNode
// (pulpo/graphs/nodes/api_trigger.py). Unlike the Python version, this route
// requires auth (see proxy.ts) -- the spike closes that gap rather than
// reproducing it.
//
// wait_user resume (2026-07-22): pass `contact_phone` in the body to test a
// flow that pauses (subflows con wait_user/gate) end-to-end via curl/HTTP,
// no Telegram involved -- same dispatcher pattern as
// app/api/telegram/webhook/[tokenId]/route.ts. Sin contact_phone se
// comporta como antes: siempre arranca un run nuevo en `nodeId`. Pensado
// para dev local (ver management/HANDOFF_VERCEL_DEEP_MIGRATION.md, "Base
// de datos local para dev") -- no hace falta reemplazar telegram_trigger
// por ningún node type nuevo: este endpoint ya puede entrar por CUALQUIER
// nodeId del flow (el nodo trigger es un passthrough, ver lib/nodes/trigger.ts),
// incluido el nodo telegram_trigger real del flow importado.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ flowId: string; nodeId: string }> }
) {
  const { flowId, nodeId } = await params;
  const body = await request.json().catch(() => ({}));
  const contactPhone: string = body.contact_phone ?? "";

  if (contactPhone) {
    const [flow] = await getDb().select({ botId: flows.botId }).from(flows).where(eq(flows.id, flowId));
    if (flow) {
      const waiting = await getWaitingGateRun(flow.botId, contactPhone);
      if (waiting && waiting.resumeNodeId) {
        const resumeState = createFlowState({
          message: body.message ?? "",
          canal: "api",
          contactPhone,
          data: {},
        });
        resumeState.data = restoreSlotsForResume(waiting.slotsJson, waiting.startedAt ?? new Date());
        continueConversation(resumeState);
        await endFlowRunHandedOff(waiting.runId);
        const run = await start(runFlowWorkflow, [waiting.flowId, waiting.resumeNodeId, resumeState]);
        return Response.json({ run_id: run.runId, resumed: true });
      }
    }
  }

  const initialState = createFlowState({
    message: body.message ?? "",
    canal: "api",
    contactPhone,
    data: body.data ?? {},
  });

  const run = await start(runFlowWorkflow, [flowId, nodeId, initialState]);

  return Response.json({ run_id: run.runId });
}
