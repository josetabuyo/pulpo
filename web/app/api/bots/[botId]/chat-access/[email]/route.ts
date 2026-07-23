import { removeChatAccess } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

export async function DELETE(_request: Request, { params }: { params: Promise<{ botId: string; email: string }> }) {
  const { botId, email } = await params;
  const denied = await assertBotAccess(botId);
  if (denied) return denied;
  try {
    await removeChatAccess(botId, decodeURIComponent(email));
    return Response.json({ ok: true });
  } catch (err) {
    return errorResponse(err);
  }
}
