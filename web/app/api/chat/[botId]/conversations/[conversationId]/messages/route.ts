import { resolveChatCaller } from "@/lib/auth/chat-access";
import { dispatchInbound } from "@/lib/business/dispatch";
import { getConversation, getLastRunStatus, insertUserMessage, listConversationMessages } from "@/lib/business/chats";

// Runtime del chat: transcript + envío de mensajes de UNA conversación.
// Valida que la conversación sea del caller (owner_key) -- incluso
// admin/dueño del bot pega 403 acá si no es el owner; para leer/enviar como
// gestión, usar /api/bots/{botId}/chats/{id}/messages (solo lectura, ver
// §4.1 del handoff).
async function loadOwnConversation(botId: string, conversationId: string, request: Request) {
  const resolved = await resolveChatCaller(botId, request);
  if (resolved instanceof Response) return { error: resolved } as const;
  const conversation = await getConversation(botId, conversationId);
  if (!conversation) return { error: Response.json({ error: "not found" }, { status: 404 }) } as const;
  if (conversation.ownerKey !== resolved.ownerKey) {
    return { error: Response.json({ error: "forbidden" }, { status: 403 }) } as const;
  }
  return { resolved, conversation } as const;
}

// GET .../messages?after={lastId} -- transcript + run_status del último run
// que tocó esta conversación (§3 del handoff: el frontend polea esto cada
// 2s hasta ver mensajes bot nuevos con run_status terminal/waiting_gate).
export async function GET(
  request: Request,
  { params }: { params: Promise<{ botId: string; conversationId: string }> },
) {
  const { botId, conversationId } = await params;
  const loaded = await loadOwnConversation(botId, conversationId, request);
  if ("error" in loaded) return loaded.error;

  const url = new URL(request.url);
  const afterParam = url.searchParams.get("after");
  const afterId = afterParam ? Number(afterParam) : undefined;

  const [messages, runStatus] = await Promise.all([
    listConversationMessages(conversationId, afterId),
    getLastRunStatus(botId, loaded.conversation.contactIdentifier),
  ]);
  return Response.json({ messages, run_status: runStatus });
}

// POST .../messages -- inserta el mensaje user (síncrono, el usuario lo ve
// al toque) y dispara/reanuda el flow vía dispatchInbound (§4.5 del
// handoff). Fire-and-forget: NO espera al workflow, responde {run_id,
// resumed} al instante -- el frontend polea el GET de arriba para la
// respuesta del bot.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ botId: string; conversationId: string }> },
) {
  const { botId, conversationId } = await params;
  const loaded = await loadOwnConversation(botId, conversationId, request);
  if ("error" in loaded) return loaded.error;

  const body = await request.json().catch(() => ({}));
  const message = String(body.message ?? "").trim();
  if (!message) return Response.json({ error: "message vacío" }, { status: 400 });

  await insertUserMessage(conversationId, message);

  const { runId, resumed } = await dispatchInbound({
    botId,
    flowId: loaded.resolved.config.flow_id,
    triggerNodeId: loaded.resolved.config.trigger_node_id,
    contactIdentifier: loaded.conversation.contactIdentifier,
    message,
    canal: "chat",
  });

  return Response.json({ run_id: runId, resumed });
}
