import { moveConnection } from "@/lib/business/connections";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/connections.py (POST "/{number}/move").
export async function POST(request: Request, { params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const body = await request.json();
  const targetBotId = String(body.targetBotId ?? "");
  if (!targetBotId) {
    return Response.json({ detail: "targetBotId requerido" }, { status: 400 });
  }
  try {
    const result = await moveConnection(number, targetBotId);
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
