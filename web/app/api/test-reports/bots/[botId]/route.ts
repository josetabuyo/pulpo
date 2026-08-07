import { listPublishedReports } from "@/lib/business/test-report-publish";
import { errorResponse } from "@/lib/api/errors";

// Público, sin sesión -- lista todos los reportes publicados de un bot, uno
// debajo del otro (ver frontend/src/pages/EmbedTestReportsPage.jsx), sin
// summary pesado (steps/flow_snapshot/diagram_image quedan en el detalle de
// cada run dentro de `runs`, no se recortan acá -- volumen bajo, pensado
// para consumo humano vía link, no para listados masivos).
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  try {
    const reports = await listPublishedReports(botId);
    return Response.json(reports);
  } catch (err) {
    return errorResponse(err);
  }
}
