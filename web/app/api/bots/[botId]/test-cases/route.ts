import { createTestCase, listTestCases } from "@/lib/business/test-cases";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Lista/alta de casos de test de este bot -- tab "Test" > "Casos".
export async function GET(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  return Response.json(await listTestCases(botId));
}

export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json();
  try {
    const testCase = await createTestCase(botId, {
      chatConfigId: String(body.chat_config_id ?? ""),
      slug: String(body.slug ?? ""),
      title: String(body.title ?? ""),
      description: body.description,
      turns: body.turns ?? [],
      checks: body.checks ?? [],
      position: body.position,
    });
    return Response.json(testCase, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
