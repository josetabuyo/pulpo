import { listTestRuns } from "@/lib/business/test-cases";
import { runSuite } from "@/lib/business/test-runner";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// GET: historial de corridas (más reciente primero) -- reemplaza el listado
// de test_reports. POST: corre varios casos ("Correr todos" si case_ids
// viene vacío/ausente) agrupados bajo un suite_run_id común.
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  return Response.json(await listTestRuns(botId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json().catch(() => ({}));
  try {
    const caseIds = Array.isArray(body.case_ids) ? body.case_ids.map(String) : undefined;
    const results = await runSuite(botId, caseIds);
    return Response.json({ suite_run_id: results[0]?.suite_run_id ?? null, results });
  } catch (err) {
    return errorResponse(err);
  }
}
