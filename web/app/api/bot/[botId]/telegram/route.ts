import { addTelegramConnection } from "@/lib/business/bots";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/ui/routers/bot_portal.py (POST "/bot/{bot_id}/telegram").
// Reachable by both admin and scoped (see proxy.ts::SCOPED_BOT_ROUTES).
export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    const result = await addTelegramConnection(botId, String(body.token ?? ""));
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
