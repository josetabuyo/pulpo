import { updateBot, deleteBot } from "@/lib/business/bots";

// TS port of pulpo/interfaces/api/routers/bots.py (PUT/DELETE "/{bot_id}").
export async function PUT(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const body = await request.json();
  const ok = await updateBot(botId, body.name ?? null);
  if (!ok) return Response.json({ detail: `Bot no encontrada: ${botId}` }, { status: 404 });
  return Response.json({ ok: true });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const ok = await deleteBot(botId);
  if (!ok) return Response.json({ detail: `Bot no encontrada: ${botId}` }, { status: 404 });
  return Response.json({ ok: true });
}
