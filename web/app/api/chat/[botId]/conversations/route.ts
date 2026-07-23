import { resolveChatCaller } from "@/lib/auth/chat-access";
import { createConversation, listOwnConversations } from "@/lib/business/chats";

// Conversaciones del CALLER (filtradas por su owner_key) -- nunca las de
// otro. La vista de gestión (todas las del bot) es
// /api/bots/{botId}/chats, ruta separada y admin/PRO-only.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const resolved = await resolveChatCaller(botId, request);
  if (resolved instanceof Response) return resolved;
  return Response.json(await listOwnConversations(botId, resolved.ownerKey));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const resolved = await resolveChatCaller(botId, request);
  if (resolved instanceof Response) return resolved;
  const conversation = await createConversation(botId, resolved.ownerKey);
  return Response.json(conversation, { status: 201 });
}
