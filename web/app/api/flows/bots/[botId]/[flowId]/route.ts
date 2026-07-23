import { getFlow, updateFlow, deleteFlow } from "@/lib/business/flows";
import { ValidationError } from "@/lib/business/bots";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/api/routers/flows.py (GET/PUT/DELETE "/bots/{bot_id}/{flow_id}").
// Reachable by both admin and scoped (see proxy.ts::SCOPED_BOT_ROUTES).
export async function GET(request: Request, { params }: { params: Promise<{ botId: string; flowId: string }> }) {
  const { botId, flowId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const flow = await getFlow(botId, flowId);
  if (!flow) return Response.json({ detail: "Flow no encontrado" }, { status: 404 });
  return Response.json(flow);
}

export async function PUT(request: Request, { params }: { params: Promise<{ botId: string; flowId: string }> }) {
  const { botId, flowId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  const saveVersion = Boolean(body.save_version);
  const updates: Record<string, unknown> = {};
  if (body.name !== undefined) updates.name = body.name;
  if (body.definition !== undefined) updates.definition = body.definition;
  if (body.connection_id !== undefined) updates.connectionId = body.connection_id;
  if (body.contact_phone !== undefined) updates.contactPhone = body.contact_phone;
  if (body.contact_filter !== undefined) updates.contactFilter = body.contact_filter;
  if (body.flow_kind !== undefined) updates.flowKind = body.flow_kind;
  if (body.active !== undefined) updates.active = body.active;

  try {
    const flow = await updateFlow(botId, flowId, updates, saveVersion);
    if (!flow) return Response.json({ detail: "Flow no encontrado" }, { status: 404 });
    return Response.json(flow);
  } catch (err) {
    if (err instanceof ValidationError) return Response.json({ detail: err.message }, { status: 400 });
    return errorResponse(err);
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ botId: string; flowId: string }> }) {
  const { botId, flowId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const ok = await deleteFlow(botId, flowId);
  if (!ok) return Response.json({ detail: "Flow no encontrado" }, { status: 404 });
  return new Response(null, { status: 204 });
}
