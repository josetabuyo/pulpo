import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flows } from "@/lib/db/schema";
import { dispatchInbound } from "@/lib/business/dispatch";
import { getFlowNode } from "@/lib/business/flows";

// TS port of POST /api/flows/{flow_id}/trigger/{node_id}
// (pulpo/interfaces/api/routers/flows.py), backed by ApiTriggerNode
// (pulpo/graphs/nodes/api_trigger.py). Unlike the Python version, this route
// requires auth (see proxy.ts) -- the spike closes that gap rather than
// reproducing it.
//
// wait_user resume (2026-07-22): pass `contact_phone` in the body to test a
// flow that pauses (subflows con wait_user/gate) end-to-end via curl/HTTP,
// no Telegram involved -- same dispatcher pattern as
// app/api/telegram/webhook/[tokenId]/route.ts (both call
// lib/business/dispatch.ts::dispatchInbound now, see that file's docstring).
// Sin contact_phone se comporta como antes: siempre arranca un run nuevo en
// `nodeId`. Pensado para dev local (ver
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md, "Base de datos local para
// dev") -- no hace falta reemplazar telegram_trigger por ningún node type
// nuevo: este endpoint ya puede entrar por CUALQUIER nodeId del flow (el
// nodo trigger es un passthrough, ver lib/nodes/trigger.ts), incluido el
// nodo telegram_trigger real del flow importado.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ flowId: string; nodeId: string }> }
) {
  const { flowId, nodeId } = await params;
  const body = await request.json().catch(() => ({}));
  const contactPhone: string = body.contact_phone ?? "";

  let botId = "";
  if (contactPhone) {
    const [flow] = await getDb().select({ botId: flows.botId }).from(flows).where(eq(flows.id, flowId));
    botId = flow?.botId ?? "";
  }

  // Pausa por-nodo (2026-07-23): un trigger pausado no acepta activaciones
  // nuevas, sea por HTTP directo, simulador, o trigger_chat -- mismo criterio
  // que findMatchingTriggers para Telegram.
  const triggerNode = await getFlowNode(flowId, nodeId);
  if (triggerNode?.config?.paused) {
    return Response.json({ error: "Este trigger está pausado" }, { status: 409 });
  }

  const { runId, resumed } = await dispatchInbound({
    botId,
    flowId,
    triggerNodeId: nodeId,
    contactIdentifier: contactPhone,
    message: body.message ?? "",
    canal: "api",
    data: (body.data as Record<string, unknown>) ?? {},
  });

  return Response.json({ run_id: runId, resumed });
}
