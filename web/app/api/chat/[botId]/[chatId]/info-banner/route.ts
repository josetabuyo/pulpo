import { getChatConfigRow, updateInfoBannerMessage } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { isBotKeyRequest } from "@/lib/auth/bot-key";

// Pública, autenticada por `X-Pulpo-Bot-Key` (mismo esquema que
// ads/publish/route.ts) -- pensada para que Luganense actualice el mensaje
// del banner "info trans" (franja tipo noticiero debajo del header del
// chat) sin login humano, para poder reportar algo rápido.
//
// Body: { message: string, enabled?: boolean }
// Respuesta: { info_banner: { enabled, message } }
export async function POST(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string }> },
) {
  const { botId, chatId } = await params;

  const config = await getChatConfigRow(chatId);
  if (!config || config.botId !== botId) return Response.json({ error: "chat not found" }, { status: 404 });

  if (!(await isBotKeyRequest(request, botId))) {
    return Response.json({ error: "missing or invalid X-Pulpo-Bot-Key" }, { status: 401 });
  }

  const body = await request.json().catch(() => ({}));
  const message = String(body.message ?? "");
  if (!message.trim()) return Response.json({ detail: "message es requerido" }, { status: 400 });

  try {
    const infoBanner = await updateInfoBannerMessage(chatId, message, body.enabled !== false);
    return Response.json({ info_banner: infoBanner });
  } catch (err) {
    return errorResponse(err);
  }
}
