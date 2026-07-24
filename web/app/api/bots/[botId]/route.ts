import { getBot, updateBot, deleteBot } from "@/lib/business/bots";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/api/routers/bots.py (PUT/DELETE "/{bot_id}"),
// plus a new GET for the scoped/"un solo bot" portal (see
// proxy.ts::SCOPED_BOT_ROUTES -- only GET is in that allowlist, PUT/DELETE
// stay admin-only, defended here too via assertBotAccess).
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;

  const bot = await getBot(botId);
  if (!bot) return Response.json({ detail: `Bot no encontrada: ${botId}` }, { status: 404 });
  return Response.json(bot);
}

export async function PUT(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const body = await request.json();
  const ok = await updateBot(botId, body.name ?? null);
  if (!ok) return Response.json({ detail: `Bot no encontrada: ${botId}` }, { status: 404 });
  return Response.json({ ok: true });
}

export async function DELETE(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const ok = await deleteBot(botId);
  if (!ok) return Response.json({ detail: `Bot no encontrada: ${botId}` }, { status: 404 });
  return Response.json({ ok: true });
}
