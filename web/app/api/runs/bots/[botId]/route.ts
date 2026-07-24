import { listRuns } from "@/lib/business/run-stats";
import { assertBotAccess } from "@/lib/auth/bot-access";

// GET /api/runs/bots/{botId}?limit= -- runs de ESTE bot, más reciente
// primero. Consumido por la tab "Ejecuciones" (RunsTab.jsx) -- antes
// apuntaba acá pero la ruta no existía (404 silencioso vía apiCall.catch),
// por eso la tab siempre aparecía vacía aunque hubiera runs reales.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const { searchParams } = new URL(request.url);
  const limit = Number(searchParams.get("limit")) || undefined;
  const runs = await listRuns({ botId, limit });
  return Response.json(runs);
}
