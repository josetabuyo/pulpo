import { patchTelegramSettings } from "@/lib/business/bots";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/bots.py (PATCH ".../telegram/{token_id}/settings").
export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ botId: string; tokenId: string }> },
) {
  const { botId, tokenId } = await params;
  const body = await request.json();
  try {
    const result = await patchTelegramSettings(botId, tokenId, Boolean(body.allow_mass));
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
