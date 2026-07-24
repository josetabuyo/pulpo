import { createChatConfig, listChatConfigs } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Lista/alta de chats de este bot -- gestión, acción de PRO o admin dueño
// del bot (a diferencia de bot_users, que es admin-only). Un bot puede tener
// N chats (2026-07-23) -- ver management/HANDOFF_DASHBOARD_CHATS_VIEW.md
// §4.1/§2.1 para el diseño original de una sola fila, ya superado.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  return Response.json(await listChatConfigs(botId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    // Azúcar de entrada (§2.1 del handoff): allowlist:["*"] normaliza a
    // is_public=true, nunca se persiste el sentinel.
    const isPublic = Boolean(body.is_public) || (Array.isArray(body.allowlist) && body.allowlist.includes("*"));
    const config = await createChatConfig(botId, {
      flowId: String(body.flow_id ?? ""),
      triggerNodeId: String(body.trigger_node_id ?? ""),
      title: body.title,
      isPublic,
      enabled: Boolean(body.enabled),
      banners: body.banners,
      themeVars: body.theme_vars,
      customCss: body.custom_css,
    });
    return Response.json(config, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
