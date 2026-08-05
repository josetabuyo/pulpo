import { unpublishAd } from "@/lib/business/chat-ads";
import { getChatConfigRow } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { isBotKeyRequest } from "@/lib/auth/bot-key";

// Espejo de .../ads/publish/route.ts -- mismo esquema bot-key. No-op (no
// error) si `external_ref` no matchea ninguna fila (ver
// lib/business/chat-ads.ts::unpublishAd), para que un caller externo pueda
// llamar esto sin haber sincronizado antes.
//
// Body: { external_ref } -- Respuesta: { active: [...] } (mismo shape que publish).
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
  const externalRef = String(body.external_ref ?? "");
  if (!externalRef) return Response.json({ detail: "external_ref es requerido" }, { status: 400 });

  try {
    const active = await unpublishAd(chatId, externalRef);
    return Response.json({ active });
  } catch (err) {
    return errorResponse(err);
  }
}
