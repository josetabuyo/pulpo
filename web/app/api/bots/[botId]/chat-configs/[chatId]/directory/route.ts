import { getChatConfigRow } from "@/lib/business/chats";
import { getDirectoryConfig, setDirectoryConfig } from "@/lib/business/chat-directory";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Gestión (admin/PRO dueño del bot) de la config completa (sin sanitizar --
// incluye source.*/lead.*, URLs/headers/body) del directorio de UN chat.
// Mismo nivel de auth que .../ads (proxy.ts::SCOPED_BOT_ROUTES).
async function assertChatBelongsToBot(botId: string, chatId: string): Promise<Response | null> {
  const config = await getChatConfigRow(chatId);
  if (!config || config.botId !== botId) return Response.json({ error: "chat not found" }, { status: 404 });
  return null;
}

export async function GET(request: Request, { params }: { params: Promise<{ botId: string; chatId: string }> }) {
  const { botId, chatId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const notFound = await assertChatBelongsToBot(botId, chatId);
  if (notFound) return notFound;
  const config = await getDirectoryConfig(chatId);
  return Response.json(config ?? { version: 1, enabled: false, sections: [] });
}

export async function PUT(request: Request, { params }: { params: Promise<{ botId: string; chatId: string }> }) {
  const { botId, chatId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const notFound = await assertChatBelongsToBot(botId, chatId);
  if (notFound) return notFound;
  const body = await request.json().catch(() => ({}));
  try {
    const config = await setDirectoryConfig(chatId, body);
    return Response.json(config);
  } catch (err) {
    return errorResponse(err);
  }
}
