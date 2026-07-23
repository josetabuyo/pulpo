import { getBotPaused, setBotPaused } from "@/lib/business/bots";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/ui/routers/bot_portal.py (GET/PUT
// "/bot/{bot_id}/paused"). Reachable by both admin and scoped (see
// proxy.ts's SCOPED_BOT_ROUTES) -- assertBotAccess is the defense-in-depth
// check for the scoped case.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;

  const bot = await getBotPaused(botId);
  if (!bot) return Response.json({ detail: `Bot no encontrada: ${botId}` }, { status: 404 });
  return Response.json({ paused: bot.paused, bot_id: botId });
}

export async function PUT(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;

  const body = await request.json();
  const shouldPause = Boolean(body.paused);
  const ok = await setBotPaused(botId, shouldPause);
  if (!ok) return Response.json({ detail: `Bot no encontrada: ${botId}` }, { status: 404 });
  return Response.json({ ok: true, paused: shouldPause, bot_id: botId });
}
