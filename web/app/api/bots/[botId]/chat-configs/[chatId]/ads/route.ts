import { createAd, listAds } from "@/lib/business/chat-ads";
import { getChatConfigRow } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Gestión (admin/PRO dueño del bot) de la publicidad de UN chat puntual --
// alta y listado. Publicar/despublicar/editar/borrar una fila puntual es
// .../ads/[adId] (ver ese route.ts). Mismo nivel de auth que chat-configs
// (proxy.ts::SCOPED_BOT_ROUTES).
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
  return Response.json(await listAds(chatId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string; chatId: string }> }) {
  const { botId, chatId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const notFound = await assertChatBelongsToBot(botId, chatId);
  if (notFound) return notFound;
  const body = await request.json();
  try {
    const ad = await createAd(chatId, {
      title: body.title,
      description: body.description,
      imageUrl: String(body.image_url ?? ""),
      linkUrl: body.link_url,
    });
    return Response.json(ad, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
