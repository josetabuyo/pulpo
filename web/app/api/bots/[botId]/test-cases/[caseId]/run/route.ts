import { runTestCase } from "@/lib/business/test-runner";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Corre UN caso puntual, in-process (ver lib/business/test-runner.ts) --
// sin pytest, sin gastar cuota de Vercel Workflow (corre dentro del propio
// `next dev`, Local World). Puede tardar varios minutos (varios turnos,
// cada uno con nodos LLM encadenados) -- el caller (frontend) debe esperar
// la respuesta sin timeout corto.
export async function POST(request: Request, { params }: { params: Promise<{ botId: string; caseId: string }> }) {
  const { botId, caseId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    const result = await runTestCase(botId, caseId);
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
