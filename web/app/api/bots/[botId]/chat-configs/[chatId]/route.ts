import { deleteChatConfig, getChatConfig, updateChatConfig } from "@/lib/business/chats";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Gestión de UN chat puntual (editar/borrar) -- PRO o admin dueño del bot.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string; chatId: string }> }) {
  const { botId, chatId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const config = await getChatConfig(chatId);
  if (!config || config.bot_id !== botId) return Response.json({ error: "not found" }, { status: 404 });
  return Response.json(config);
}

export async function PUT(request: Request, { params }: { params: Promise<{ botId: string; chatId: string }> }) {
  const { botId, chatId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    const isPublic = Boolean(body.is_public) || (Array.isArray(body.allowlist) && body.allowlist.includes("*"));
    const config = await updateChatConfig(chatId, botId, {
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

// Borra solo la config del chat -- las conversaciones asociadas quedan
// intactas (dominio de ejecuciones de flow, ver lib/business/chats.ts).
export async function DELETE(request: Request, { params }: { params: Promise<{ botId: string; chatId: string }> }) {
  const { botId, chatId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    await deleteChatConfig(chatId, botId);
    return Response.json({ ok: true });
  } catch (err) {
    return errorResponse(err);
  }
}
