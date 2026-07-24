import { addBotUser, listBotUsers } from "@/lib/business/bot-users";
import { errorResponse } from "@/lib/api/errors";

// Admin-only allowlist of which Google email can log into this bot's portal
// -- paso 1 hacia Pulpo Lite/PRO, ver web/auth.ts.
export async function GET(_request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  return Response.json(await listBotUsers(botId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const body = await request.json();
  try {
    await addBotUser(botId, String(body.email ?? ""));
    return Response.json({ ok: true }, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
