import { resolveChatCaller } from "@/lib/auth/chat-access";
import { searchSection } from "@/lib/business/chat-directory";

// Pública (misma auth que el resto de /api/chat/**) -- proxy server-side
// hacia el endpoint de catálogo configurado en chat_configs.directory. Nunca
// expone la URL/headers upstream al cliente, solo items normalizados +
// item_token (ver chat-directory.ts).
export async function GET(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string; sectionId: string }> },
) {
  const { botId, chatId, sectionId } = await params;
  const resolved = await resolveChatCaller(botId, chatId, request);
  if (resolved instanceof Response) return resolved;

  const q = new URL(request.url).searchParams.get("q") ?? "";
  const result = await searchSection(chatId, sectionId, q);
  return Response.json(result);
}
