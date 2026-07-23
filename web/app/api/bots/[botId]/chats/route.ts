import { listBotChats } from "@/lib/business/chats";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Listado de conversaciones del chat de este bot (id, owner_key, fechas) --
// vista de gestión, orden desc por last_message_at. Sin preview (pedido
// explícito, ver §5.1 del handoff).
export async function GET(_request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(botId);
  if (denied) return denied;
  return Response.json(await listBotChats(botId));
}
