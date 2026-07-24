import { listTestReports } from "@/lib/business/test-reports";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Lista de reportes e2e de este bot (id/slug/title/created_at, sin el HTML
// -- ver [reportId]/route.ts para el contenido) -- tab "Test" (RunsTab.jsx
// vecino, BotCard).
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  return Response.json(await listTestReports(botId));
}
