import { getTestRun } from "@/lib/business/test-cases";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

export async function GET(request: Request, { params }: { params: Promise<{ botId: string; runId: string }> }) {
  const { botId, runId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    return Response.json(await getTestRun(botId, runId));
  } catch (err) {
    return errorResponse(err);
  }
}
