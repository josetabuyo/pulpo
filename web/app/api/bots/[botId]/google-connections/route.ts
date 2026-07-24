import { listGoogleConnections, createGoogleConnection } from "@/lib/business/google-connections";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/api/routers/bots.py (GET/POST ".../google-connections").
// Reachable by both admin and scoped (see proxy.ts::SCOPED_BOT_ROUTES).
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  return Response.json(await listGoogleConnections(botId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    const result = await createGoogleConnection(botId, body.credentials_json, body.label ?? null);
    return Response.json(result, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
