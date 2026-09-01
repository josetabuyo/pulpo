import { put } from "@vercel/blob";
import { resolveChatCaller } from "@/lib/auth/chat-access";
import { getConversation } from "@/lib/business/chats";

// Sube UN adjunto (hoy: imagen de factura) para el próximo mensaje de esta
// conversación -- separado de POST .../messages (que sigue siendo JSON
// puro) para no convertir esa ruta a multipart. El frontend sube acá
// primero, y manda la url que devuelve como `attachment_url` al POST de
// messages. Misma auth que esa ruta (resolveChatCaller + dueño de la
// conversación) -- ver loadOwnConversation en messages/route.ts, duplicado
// acá porque es un solo chequeo y no vale la pena extraerlo por ahora.
const MAX_BYTES = 15 * 1024 * 1024;

export async function POST(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string; conversationId: string }> },
) {
  const { botId, chatId, conversationId } = await params;

  const resolved = await resolveChatCaller(botId, chatId, request);
  if (resolved instanceof Response) return resolved;
  const conversation = await getConversation(botId, conversationId);
  if (!conversation) return Response.json({ error: "not found" }, { status: 404 });
  if (conversation.ownerKey !== resolved.ownerKey) {
    return Response.json({ error: "forbidden" }, { status: 403 });
  }

  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  if (!(file instanceof File)) return Response.json({ error: "falta el archivo" }, { status: 400 });
  if (!file.type.startsWith("image/")) return Response.json({ error: "solo se aceptan imágenes" }, { status: 400 });
  if (file.size > MAX_BYTES) return Response.json({ error: "archivo demasiado grande (máx 15MB)" }, { status: 400 });

  const pathname = `chat-attachments/${botId}/${conversationId}/${Date.now()}-${file.name}`;
  const blob = await put(pathname, file, { access: "public", addRandomSuffix: true });

  return Response.json({ url: blob.url }, { status: 201 });
}
