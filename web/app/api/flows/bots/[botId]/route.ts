import { listFlows, createFlow } from "@/lib/business/flows";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/flows.py (GET/POST "/bots/{bot_id}").
export async function GET(_request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  try {
    return Response.json(await listFlows(botId));
  } catch (err) {
    return errorResponse(err);
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const body = await request.json();
  try {
    const flow = await createFlow({
      botId,
      name: body.name,
      definition: body.definition ?? null,
      connectionId: body.connection_id ?? null,
      contactPhone: body.contact_phone ?? null,
      contactFilter: body.contact_filter ?? null,
      flowKind: body.flow_kind || "flow",
    });
    return Response.json(flow, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
