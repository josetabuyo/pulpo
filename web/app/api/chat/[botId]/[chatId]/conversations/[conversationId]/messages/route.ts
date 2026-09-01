import { resolveChatCaller } from "@/lib/auth/chat-access";
import { dispatchInbound } from "@/lib/business/dispatch";
import { getConversation, getLastRunStatus, insertUserMessage, listConversationMessages } from "@/lib/business/chats";
import { getFlowNode } from "@/lib/business/flows";

// Runtime del chat: transcript + envío de mensajes de UNA conversación de UN
// chat puntual. Valida que la conversación sea del caller (owner_key) --
// incluso admin/dueño del bot pega 403 acá si no es el owner; para leer/
// enviar como gestión, usar /api/bots/{botId}/chats/{id}/messages (solo
// lectura, ver §4.1 del handoff).
async function loadOwnConversation(botId: string, chatId: string, conversationId: string, request: Request) {
  const resolved = await resolveChatCaller(botId, chatId, request);
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
  { params }: { params: Promise<{ botId: string; chatId: string; conversationId: string }> },
) {
  const { botId, chatId, conversationId } = await params;
  const loaded = await loadOwnConversation(botId, chatId, conversationId, request);
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
  { params }: { params: Promise<{ botId: string; chatId: string; conversationId: string }> },
) {
  const { botId, chatId, conversationId } = await params;
  const loaded = await loadOwnConversation(botId, chatId, conversationId, request);
  if ("error" in loaded) return loaded.error;

  const body = await request.json().catch(() => ({}));
  const message = String(body.message ?? "").trim();
  const attachmentUrl = String(body.attachment_url ?? "").trim();
  if (!message && !attachmentUrl) return Response.json({ error: "message vacío" }, { status: 400 });

  // Un trigger pausado no acepta activaciones nuevas -- ver
  // lib/business/telegram.ts::findMatchingTriggers para el mismo guard del
  // lado de Telegram. No bloquea la reanudación de un run ya en curso
  // (dispatchInbound intenta resume primero), solo el arranque fresco.
  const triggerNode = await getFlowNode(loaded.resolved.config.flow_id, loaded.resolved.config.trigger_node_id);
  if (triggerNode?.config?.paused) {
    return Response.json({ error: "Este trigger está pausado" }, { status: 409 });
  }

  await insertUserMessage(conversationId, message, attachmentUrl);

  // state.message vacío hace que startConversation()/appendConversationEntry
  // (lib/nodes/state.ts) no inicialicen state.data.conversation -- ese guard
  // es `if (!content) return`, así que un mensaje solo-adjunto (típico en
  // este bot: el usuario manda la factura sin texto) corre el flow entero
  // sin transcript, y el panel "Conversación" del dashboard queda vacío
  // (bug real encontrado por José probando MachElectronics, 2026-09-01). Un
  // placeholder acá alimenta el motor sin tocar chat_messages.content (la
  // burbuja del usuario sigue mostrando solo la miniatura, no texto de más).
  const flowMessage = message || (attachmentUrl ? "[imagen adjunta]" : "");

  const { runId, resumed } = await dispatchInbound({
    botId,
    flowId: loaded.resolved.config.flow_id,
    triggerNodeId: loaded.resolved.config.trigger_node_id,
    contactIdentifier: loaded.conversation.contactIdentifier,
    message: flowMessage,
    canal: "chat",
    data: attachmentUrl ? { attachment_url: attachmentUrl } : undefined,
  });

  return Response.json({ run_id: runId, resumed });
}
