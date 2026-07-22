import { addTelegramConnection } from "@/lib/business/bots";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/ui/routers/bot_portal.py (POST "/bot/{bot_id}/telegram").
// Gated by proxy.ts's default admin-session scheme (this path doesn't match
// the trigger/webhook regexes) -- Fase 2 (bot-portal-own JWT) is out of
// scope for this migration, see management/HANDOFF_VERCEL_DEEP_MIGRATION.md.
export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const body = await request.json();
  try {
    const result = await addTelegramConnection(botId, String(body.token ?? ""));
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
