import { resolveChatCaller } from "@/lib/auth/chat-access";
import { getConversation, getOwnRunSteps } from "@/lib/business/chats";

// GET .../runs/{runId}/steps -- steps (flow_run_steps) de un run, SOLO si
// pertenece a la conversación del caller. Mismo auth que
// .../messages (resolveChatCaller: sesión real o X-Chat-Visitor si el chat
// es público) -- existe porque GET /api/runs/{runId} (mismo shape) exige
// sesión admin, y scripts/generate_e2e_report.py (vía
// tests/e2e/helpers.py::ChatConversation) necesita leer el log de SU PROPIA
// conversación contra prod sin login real, para validar ran_node/
// state_field/branch_taken igual que hacía SimConversation contra el
// backend Python viejo.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ botId: string; chatId: string; conversationId: string; runId: string }> },
) {
  const { botId, chatId, conversationId, runId } = await params;
  const resolved = await resolveChatCaller(botId, chatId, request);
  if (resolved instanceof Response) return resolved;

  const conversation = await getConversation(botId, conversationId);
  if (!conversation) return Response.json({ error: "not found" }, { status: 404 });
  if (conversation.ownerKey !== resolved.ownerKey) {
    return Response.json({ error: "forbidden" }, { status: 403 });
  }

  const steps = await getOwnRunSteps(botId, conversation.contactIdentifier, runId);
  if (steps === null) return Response.json({ error: "run not found" }, { status: 404 });
  return Response.json({ steps });
}
