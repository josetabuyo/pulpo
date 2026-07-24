import { addChatAccess, listChatAccess } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Allowlist de emails con derecho a CHATEAR con este bot (cuando no es
// público) -- distinta de /bots/{botId}/users, que da acceso al dashboard.
// Gestión de PRO/admin dueño del bot.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  return Response.json(await listChatAccess(botId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    await addChatAccess(botId, String(body.email ?? ""));
    return Response.json({ ok: true }, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
