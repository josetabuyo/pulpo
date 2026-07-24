import { removeBotUser } from "@/lib/business/bot-users";
import { errorResponse } from "@/lib/api/errors";

export async function DELETE(_request: Request, { params }: { params: Promise<{ botId: string; email: string }> }) {
  const { botId, email } = await params;
  try {
    await removeBotUser(botId, decodeURIComponent(email));
    return Response.json({ ok: true });
  } catch (err) {
    return errorResponse(err);
  }
}
