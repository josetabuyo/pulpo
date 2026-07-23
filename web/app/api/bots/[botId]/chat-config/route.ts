import { getChatConfig, upsertChatConfig } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Config del chat de este bot -- gestión, acción de PRO o admin dueño del
// bot (a diferencia de bot_users, que es admin-only). Ver
// management/HANDOFF_DASHBOARD_CHATS_VIEW.md §4.1/§2.1.
export async function GET(_request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(botId);
  if (denied) return denied;
  const config = await getChatConfig(botId);
  return Response.json(config); // null si el bot todavía no tiene chat configurado
}

export async function PUT(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    // Azúcar de entrada (§2.1 del handoff): allowlist:["*"] normaliza a
    // is_public=true, nunca se persiste el sentinel.
    const isPublic = Boolean(body.is_public) || (Array.isArray(body.allowlist) && body.allowlist.includes("*"));
    const config = await upsertChatConfig(botId, {
      flowId: String(body.flow_id ?? ""),
      triggerNodeId: String(body.trigger_node_id ?? ""),
      title: body.title,
      isPublic,
      enabled: Boolean(body.enabled),
      banners: body.banners,
      themeVars: body.theme_vars,
      customCss: body.custom_css,
    });
    return Response.json(config);
  } catch (err) {
    return errorResponse(err);
  }
}
