import { getPublishedReport, upsertPublishedReport } from "@/lib/business/test-report-publish";
import { errorResponse } from "@/lib/api/errors";

// Dos esquemas de auth distintos a propósito, misma ruta:
//  - PUT: SOLO otro ambiente Pulpo, vía sync-token (ver
//    proxy.ts::SYNC_TOKEN_ROUTES y lib/auth/sync-token.ts) -- análogo al PUT
//    de flows (app/api/flows/bots/[botId]/[flowId]/route.ts). El caller es
//    SIEMPRE el propio backend del ambiente que publica (nunca un browser:
//    ver lib/business/test-report-publish.ts::publishSuiteRunToEnvironment).
//  - GET: público, sin sesión -- esta es la "vista de solo view" que se le
//    comparte al cliente (ver proxy.ts, bypass explícito por regex, mismo
//    criterio que CHAT_RE). No hay nada sensible acá: turnos de conversación
//    y resultados de checks, ya pensados para mostrarse.
export async function PUT(request: Request, { params }: { params: Promise<{ botId: string; reportId: string }> }) {
  const { botId, reportId } = await params;
  const body = await request.json();
  try {
    const report = await upsertPublishedReport(botId, reportId, body);
    return Response.json(report);
  } catch (err) {
    return errorResponse(err);
  }
}

export async function GET(request: Request, { params }: { params: Promise<{ botId: string; reportId: string }> }) {
  const { botId, reportId } = await params;
  try {
    const report = await getPublishedReport(botId, reportId);
    return Response.json(report);
  } catch (err) {
    return errorResponse(err);
  }
}
