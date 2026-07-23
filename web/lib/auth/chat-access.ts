import { auth } from "@/auth";
import { getChatConfig, hasChatAccess } from "@/lib/business/chats";
import { listBotsForEmail } from "@/lib/business/bot-users";

// Espejo de lib/auth/bot-access.ts pero para el runtime del chat (no la
// gestión): resuelve quién puede chatear con este bot y bajo qué owner_key
// va a guardar/leer sus conversaciones. Ver
// management/HANDOFF_DASHBOARD_CHATS_VIEW.md §4.3 (gitignoreado) para el
// diseño completo -- este comentario resume solo lo esencial.
//
// Devuelve {ownerKey, config} si el caller puede chatear, o una Response
// ({error}/{login_required}) que el handler debe devolver tal cual.
export interface ChatConfigDto {
  bot_id: string;
  flow_id: string;
  trigger_node_id: string;
  title: string;
  is_public: boolean;
  enabled: boolean;
  banners: unknown;
  theme_vars: unknown;
  custom_css: string;
}

export async function resolveChatCaller(
  botId: string,
  request: Request,
): Promise<{ ownerKey: string; config: ChatConfigDto } | Response> {
  const config = await getChatConfig(botId);
  if (!config || !config.enabled) {
    return Response.json({ error: "chat not found" }, { status: 404 });
  }

  const session = await auth();
  const email = session?.user?.email?.toLowerCase();
  if (email) {
    if (session!.user!.role === "admin") {
      return { ownerKey: `email:${email}`, config: config as ChatConfigDto };
    }
    const [ownsBot, chatAllowed] = await Promise.all([
      listBotsForEmail(email).then((ids) => ids.includes(botId)),
      hasChatAccess(botId, email),
    ]);
    if (ownsBot || chatAllowed) {
      return { ownerKey: `email:${email}`, config: config as ChatConfigDto };
    }
  }

  if (config.is_public) {
    const visitorKey = request.headers.get("x-chat-visitor");
    if (!visitorKey) {
      return Response.json({ error: "missing X-Chat-Visitor header" }, { status: 400 });
    }
    return { ownerKey: `anon:${visitorKey}`, config: config as ChatConfigDto };
  }

  return Response.json({ error: "not authenticated", login_required: true }, { status: 401 });
}
