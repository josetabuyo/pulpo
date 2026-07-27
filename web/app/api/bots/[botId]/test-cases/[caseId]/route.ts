import { deleteTestCase, getTestCaseDto, updateTestCase } from "@/lib/business/test-cases";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

export async function GET(request: Request, { params }: { params: Promise<{ botId: string; caseId: string }> }) {
  const { botId, caseId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    return Response.json(await getTestCaseDto(botId, caseId));
  } catch (err) {
    return errorResponse(err);
  }
}

export async function PUT(request: Request, { params }: { params: Promise<{ botId: string; caseId: string }> }) {
  const { botId, caseId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    const testCase = await updateTestCase(botId, caseId, {
      chatConfigId: String(body.chat_config_id ?? ""),
      slug: String(body.slug ?? ""),
      title: String(body.title ?? ""),
      description: body.description,
      turns: body.turns ?? [],
      checks: body.checks ?? [],
      position: body.position,
    });
    return Response.json(testCase);
  } catch (err) {
    return errorResponse(err);
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ botId: string; caseId: string }> }) {
  const { botId, caseId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    await deleteTestCase(botId, caseId);
    return Response.json({ ok: true });
  } catch (err) {
    return errorResponse(err);
  }
}
