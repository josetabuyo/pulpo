import { resolveChatCaller } from "@/lib/auth/chat-access";
import { createConversation, listOwnConversations } from "@/lib/business/chats";

// Conversaciones del CALLER (filtradas por su owner_key) para ESTE chat
// puntual -- nunca las de otro chat/owner. La vista de gestión (todas las
// del bot, opcionalmente filtradas por chat) es
// /api/bots/{botId}/chats?chatConfigId=, ruta separada y admin/PRO-only.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string }> },
) {
  const { botId, chatId } = await params;
  const resolved = await resolveChatCaller(botId, chatId, request);
  if (resolved instanceof Response) return resolved;
  return Response.json(await listOwnConversations(botId, chatId, resolved.ownerKey));
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string }> },
) {
  const { botId, chatId } = await params;
  const resolved = await resolveChatCaller(botId, chatId, request);
  if (resolved instanceof Response) return resolved;
  const conversation = await createConversation(botId, chatId, resolved.ownerKey);
  return Response.json(conversation, { status: 201 });
}
