import { resolveChatCaller } from "@/lib/auth/chat-access";
import { connectSection } from "@/lib/business/chat-directory";
import { errorResponse } from "@/lib/api/errors";

// Pública -- dispara el "lead" configurado para esta sección (mismo tipo de
// llamado que el nodo HTTP del flow conversacional, pero server-side y
// directo, sin conversación de por medio). Body: { item_id, item_token,
// item_raw?, fields? }. `item_token` viene de una búsqueda reciente (ver
// .../search) -- sin uno válido no hay lead, así un cliente no puede forjar
// un item que nunca vino del catálogo real.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string; sectionId: string }> },
) {
  const { botId, chatId, sectionId } = await params;
  const resolved = await resolveChatCaller(botId, chatId, request);
  if (resolved instanceof Response) return resolved;

  const body = await request.json().catch(() => ({}));
  const itemId = String(body.item_id ?? "");
  const itemToken = String(body.item_token ?? "");
  if (!itemId || !itemToken) {
    return Response.json({ detail: "item_id e item_token son requeridos" }, { status: 400 });
  }

  const isEmail = resolved.ownerKey.startsWith("email:");
  const emailOrVisitor = isEmail ? resolved.ownerKey.slice("email:".length) : undefined;

  try {
    const result = await connectSection(
      chatId,
      sectionId,
      {
        itemId,
        itemToken,
        itemRaw: body.item_raw && typeof body.item_raw === "object" ? body.item_raw : {},
        fields: body.fields && typeof body.fields === "object" ? body.fields : {},
        contact: {
          id: resolved.ownerKey,
          channel: "chat",
          email: isEmail ? emailOrVisitor : undefined,
        },
      },
      { bot_id: botId, id: chatId, title: resolved.config.title },
    );
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
