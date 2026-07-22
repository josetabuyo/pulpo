import { listGoogleConnections, createGoogleConnection } from "@/lib/business/google-connections";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/bots.py (GET/POST ".../google-connections").
export async function GET(_request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  return Response.json(await listGoogleConnections(botId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const body = await request.json();
  try {
    const result = await createGoogleConnection(botId, body.credentials_json, body.label ?? null);
    return Response.json(result, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
