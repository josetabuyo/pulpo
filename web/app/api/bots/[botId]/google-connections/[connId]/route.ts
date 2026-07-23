import { deleteGoogleConnection } from "@/lib/business/google-connections";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/api/routers/bots.py (DELETE ".../google-connections/{conn_id}").
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ botId: string; connId: string }> },
) {
  const { botId, connId } = await params;
  const denied = await assertBotAccess(botId);
  if (denied) return denied;
  if (connId === "pulpo-default") {
    return Response.json({ detail: "La conexión Pulpo no se puede eliminar" }, { status: 403 });
  }
  try {
    await deleteGoogleConnection(botId, connId);
    return Response.json({ ok: true });
  } catch (err) {
    return errorResponse(err);
  }
}
