import { listConnections, createConnection } from "@/lib/business/connections";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/connections.py (GET/POST "").
export async function GET() {
  return Response.json(await listConnections());
}

export async function POST(request: Request) {
  const body = await request.json();
  const botId = String(body.botId ?? "");
  const number = String(body.number ?? "");
  if (!botId || !number) {
    return Response.json({ detail: "botId y number son requeridos" }, { status: 400 });
  }
  try {
    const result = await createConnection(botId, number, body.botName ?? null);
    return Response.json(result, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
