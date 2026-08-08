import { getPublishedReport, upsertPublishedReport } from "@/lib/business/test-report-publish";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccessOrBotKey } from "@/lib/auth/bot-access";

// Dos esquemas de auth distintos a propósito, misma ruta:
//  - PUT: SOLO otro ambiente Pulpo, vía sync-token (ver
//    proxy.ts::SYNC_TOKEN_ROUTES y lib/auth/sync-token.ts) -- análogo al PUT
//    de flows (app/api/flows/bots/[botId]/[flowId]/route.ts). El caller es
//    SIEMPRE el propio backend del ambiente que publica (nunca un browser:
//    ver lib/business/test-report-publish.ts::publishSuiteRunToEnvironment).
//  - GET: la "vista de solo view" que se le comparte al cliente -- sesión
//    con permiso sobre el bot, o `X-Pulpo-Bot-Key` por-bot (ver
//    proxy.ts::BOT_KEY_ROUTES / lib/auth/bot-key.ts). Dejó de ser público
//    sin auth (2026-08-07) -- el diagrama del flow que ahora trae cada run
//    (flow_snapshot/steps) no es algo para exponer a cualquiera con el link.
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
  const denied = await assertBotAccessOrBotKey(request, botId);
  if (denied) return denied;
  try {
    const report = await getPublishedReport(botId, reportId);
    return Response.json(report);
  } catch (err) {
    return errorResponse(err);
  }
}
