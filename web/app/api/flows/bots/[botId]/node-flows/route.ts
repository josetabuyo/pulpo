import { listNodeFlows } from "@/lib/business/flows";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/flows.py (GET ".../bots/{bot_id}/node-flows").
// Lists the bot's NodoFlow templates (flow_kind === "node_flow") with
// inputs/routes/color -- the editor uses `color` to paint nodo_flow
// instances with the color declared by the sub-flow they reference (see
// frontend/src/components/FlowEditor.jsx fetching this route into
// flowStore.js's nodeFlowColors map).
export async function GET(_request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  try {
    return Response.json(await listNodeFlows(botId));
  } catch (err) {
    return errorResponse(err);
  }
}
