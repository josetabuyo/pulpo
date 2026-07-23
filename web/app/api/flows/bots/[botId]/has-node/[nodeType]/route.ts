import { hasNodeType } from "@/lib/business/flows";
import { assertBotAccess } from "@/lib/auth/bot-access";

// TS port of pulpo/interfaces/api/routers/flows.py (GET ".../has-node/{node_type}").
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ botId: string; nodeType: string }> },
) {
  const { botId, nodeType } = await params;
  const denied = await assertBotAccess(botId);
  if (denied) return denied;
  const found = await hasNodeType(botId, nodeType);
  return Response.json({ found });
}
