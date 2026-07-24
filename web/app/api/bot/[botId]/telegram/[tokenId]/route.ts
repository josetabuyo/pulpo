import { deleteTelegramConnection } from "@/lib/business/bots";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/ui/routers/bot_portal.py (DELETE "/bot/{bot_id}/telegram/{token_id}").
export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ botId: string; tokenId: string }> },
) {
  const { botId, tokenId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    const result = await deleteTelegramConnection(botId, tokenId);
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
