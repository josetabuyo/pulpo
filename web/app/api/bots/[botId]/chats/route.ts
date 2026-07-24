import { listBotChats } from "@/lib/business/chats";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Listado de conversaciones del bot (id, chat_config_id, owner_key, fechas)
// -- vista de gestión, orden desc por last_message_at. Sin preview (pedido
// explícito, ver §5.1 del handoff). `?chatConfigId=` filtra a un chat
// puntual, para la vista embebida por-chat dentro de la card.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const chatConfigId = new URL(request.url).searchParams.get("chatConfigId") ?? undefined;
  return Response.json(await listBotChats(botId, chatConfigId));
}
