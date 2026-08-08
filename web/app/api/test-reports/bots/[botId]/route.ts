import { listPublishedReports } from "@/lib/business/test-report-publish";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccessOrBotKey } from "@/lib/auth/bot-access";

// Lista todos los reportes publicados de un bot, uno debajo del otro (ver
// frontend/src/pages/EmbedTestReportsPage.jsx). Gateado por proxy.ts
// (sesión con permiso sobre el bot, o `X-Pulpo-Bot-Key` -- ver
// proxy.ts::BOT_KEY_ROUTES) -- este chequeo es defensa-en-profundidad, mismo
// patrón que el resto de las rutas por-bot.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccessOrBotKey(request, botId);
  if (denied) return denied;
  try {
    const reports = await listPublishedReports(botId);
    return Response.json(reports);
  } catch (err) {
    return errorResponse(err);
  }
}
