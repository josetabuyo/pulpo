import { getTestReportHtml } from "@/lib/business/test-reports";
import { assertBotAccess } from "@/lib/auth/bot-access";

// HTML crudo de UN reporte -- servido con content-type text/html para que
// el frontend lo cargue directo en un <iframe src=...> (mismo patrón que
// el archivo estático que esto reemplaza, ver reports/*.html).
export async function GET(
  request: Request,
  { params }: { params: Promise<{ botId: string; reportId: string }> },
) {
  const { botId, reportId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const html = await getTestReportHtml(botId, reportId);
  if (html === null) return Response.json({ error: "not found" }, { status: 404 });
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}
