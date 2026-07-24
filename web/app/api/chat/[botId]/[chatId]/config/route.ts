import { getChatConfigRow, toPublicConfigDto } from "@/lib/business/chats";

// Pública -- subset seguro: {title, banners, theme_vars, custom_css,
// is_public, enabled}. NUNCA flow_id/trigger_node_id/allowlist (ver
// management/HANDOFF_DASHBOARD_CHATS_VIEW.md §4.2). La página lo pide antes
// de saber si hay sesión, para renderizar marca + decidir si pedir login --
// por eso NO pasa por resolveChatCaller (que 404-ea si enabled=false; acá
// queremos poder mostrar "este chat está deshabilitado" con datos de marca
// si los hay).
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string }> },
) {
  const { botId, chatId } = await params;
  const row = await getChatConfigRow(chatId);
  if (!row || row.botId !== botId) return Response.json({ error: "not found" }, { status: 404 });
  return Response.json(toPublicConfigDto(row));
}
