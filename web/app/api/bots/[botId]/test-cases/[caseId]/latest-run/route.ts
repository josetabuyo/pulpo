import { getLatestTestRunForCase } from "@/lib/business/test-cases";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Corrida más reciente de un caso -- usada por el ícono "Ver" en la fila del
// caso (tab "Test" > "Casos"), sin pasar por la vista "Resultados".
export async function GET(request: Request, { params }: { params: Promise<{ botId: string; caseId: string }> }) {
  const { botId, caseId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    const run = await getLatestTestRunForCase(botId, caseId);
    if (!run) return Response.json({ detail: "Sin corridas para este caso" }, { status: 404 });
    return Response.json(run);
  } catch (err) {
    return errorResponse(err);
  }
}
