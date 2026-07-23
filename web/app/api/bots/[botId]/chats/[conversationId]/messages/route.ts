import { getConversation, listConversationMessages } from "@/lib/business/chats";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Transcript completo de una conversación -- vista admin (sin filtrar por
// owner, a diferencia de la ruta de runtime en /api/chat/**).
export async function GET(
  request: Request,
  { params }: { params: Promise<{ botId: string; conversationId: string }> },
) {
  const { botId, conversationId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const conversation = await getConversation(botId, conversationId);
  if (!conversation) return Response.json({ error: "not found" }, { status: 404 });
  return Response.json(await listConversationMessages(conversationId));
}
