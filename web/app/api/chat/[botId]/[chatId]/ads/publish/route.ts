import { publishAd } from "@/lib/business/chat-ads";
import { getChatConfigRow } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { isBotKeyRequest } from "@/lib/auth/bot-key";

// Pública, autenticada por `X-Pulpo-Bot-Key` (NO sesión) -- pensada para que
// el sistema propio de un cliente (su ABM de publicidad) publique/rote
// publicidad sin login humano. Vive bajo /api/chat/** a propósito: ese
// prefijo ya es "self-validated" en proxy.ts (mismo esquema que el webhook
// de Telegram y el runtime del chat), así que el middleware no exige sesión
// antes de llegar acá -- este handler es quien decide.
//
// Body: { external_ref?, title?, description?, image_url, link_url? }
// Respuesta: { active: [{id, external_ref, title, description, image_url,
// link_url, published_at}, ...] } -- máx 4, nueva-primero. El caller puede
// diffear `active` contra lo que mandó para saber si su propia publicidad
// quedó afuera de la cola FILO.
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
  const imageUrl = String(body.image_url ?? "");
  if (!imageUrl) return Response.json({ detail: "image_url es requerido" }, { status: 400 });

  try {
    const active = await publishAd(chatId, {
      externalRef: body.external_ref ? String(body.external_ref) : undefined,
      title: body.title,
      description: body.description,
      imageUrl,
      linkUrl: body.link_url,
    });
    return Response.json({ active });
  } catch (err) {
    return errorResponse(err);
  }
}
