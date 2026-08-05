import { deleteAd, setAdPublished, updateAd } from "@/lib/business/chat-ads";
import { getChatConfigRow } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Gestión de UNA publicidad puntual -- editar campos, publicar/despublicar
// (`published` en el body, ver lib/business/chat-ads.ts::setAdPublished,
// misma cola FILO de 4 que el camino externo por bot-key), y borrar.
async function assertChatBelongsToBot(botId: string, chatId: string): Promise<Response | null> {
  const config = await getChatConfigRow(chatId);
  if (!config || config.botId !== botId) return Response.json({ error: "chat not found" }, { status: 404 });
  return null;
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string; adId: string }> },
) {
  const { botId, chatId, adId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const notFound = await assertChatBelongsToBot(botId, chatId);
  if (notFound) return notFound;
  const body = await request.json();
  try {
    if (typeof body.published === "boolean" && Object.keys(body).length === 1) {
      return Response.json(await setAdPublished(chatId, adId, body.published));
    }
    const ad = await updateAd(chatId, adId, {
      title: body.title,
      description: body.description,
      imageUrl: String(body.image_url ?? ""),
      linkUrl: body.link_url,
    });
    if (typeof body.published === "boolean") {
      return Response.json(await setAdPublished(chatId, adId, body.published));
    }
    return Response.json(ad);
  } catch (err) {
    return errorResponse(err);
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string; adId: string }> },
) {
  const { botId, chatId, adId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const notFound = await assertChatBelongsToBot(botId, chatId);
  if (notFound) return notFound;
  try {
    await deleteAd(chatId, adId);
    return Response.json({ ok: true });
  } catch (err) {
    return errorResponse(err);
  }
}
