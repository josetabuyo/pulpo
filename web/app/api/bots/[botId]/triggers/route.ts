import { listBotTriggers } from "@/lib/business/flows";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Tab "Triggers" (2026-07-23, reemplaza "Conexiones"): todos los nodos
// trigger de todos los flows del bot, sin importar si el flow está activo.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    return Response.json(await listBotTriggers(botId));
  } catch (err) {
    return errorResponse(err);
  }
}
