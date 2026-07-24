import { start } from "workflow/api";
import { runFlowWorkflow } from "@/workflows/run-flow";
import { createFlowState } from "@/lib/nodes/state";
import type { FlowState } from "@/lib/nodes/state";
import { continueConversation } from "@/lib/flow/conversation";
import { endFlowRunHandedOff, getWaitingGateRun, restoreSlotsForResume } from "@/lib/business/telegram";

// Dispatcher compartido: "si hay waiting_gate para (botId, contactIdentifier)
// reanudá, si no arrancá en el trigger" -- antes duplicado en
// app/api/telegram/webhook/[tokenId]/route.ts y
// app/api/flows/[flowId]/trigger/[nodeId]/route.ts. El chat (canal "chat")
// es la tercera copia; en vez de triplicar el bloque de resume, las tres
// rutas llaman a esto. Los helpers de resume siguen viviendo en
// lib/business/telegram.ts (nombre desafortunado, no son de Telegram --
// re-exportados desde acá, no vale la pena mover+actualizar imports
// existentes solo por prolijidad de nombre en este spike).
//
// canal/connectionId/contactName/botName son pass-through para que el
// FlowState resultante tenga los mismos campos que el caller construía a
// mano antes de esta extracción (ver reply.ts, que depende de canal +
// connectionId para decidir cómo entregar la respuesta).
export interface InboundContext {
  botId: string;
  contactIdentifier: string;
  message: string;
  canal: FlowState["canal"];
  connectionId?: string;
  botName?: string;
  contactName?: string;
  timestamp?: string;
}

// Solo la mitad "resume": si hay un run en waiting_gate para
// (botId, contactIdentifier), lo reanuda y devuelve {runId, resumed: true}.
// Si no hay nada que reanudar, devuelve null -- el caller decide qué hacer
// (arrancar UN flow fijo, como el trigger route/chat, o fan-out a varios
// matches, como el webhook de Telegram).
export async function resumeWaitingConversation(
  ctx: InboundContext,
): Promise<{ runId: string; resumed: true } | null> {
  if (!ctx.contactIdentifier) return null;
  const waiting = await getWaitingGateRun(ctx.botId, ctx.contactIdentifier);
  if (!waiting || !waiting.resumeNodeId) return null;

  const resumeState = createFlowState({
    message: ctx.message,
    canal: ctx.canal,
    botId: ctx.botId,
    botName: ctx.botName ?? "",
    connectionId: ctx.connectionId ?? "",
    contactPhone: ctx.contactIdentifier,
    contactName: ctx.contactName ?? "",
    timestamp: ctx.timestamp,
    data: {},
  });
  resumeState.data = restoreSlotsForResume(waiting.slotsJson, waiting.startedAt ?? new Date());
  continueConversation(resumeState);
  await endFlowRunHandedOff(waiting.runId);
  const run = await start(runFlowWorkflow, [waiting.flowId, waiting.resumeNodeId, resumeState]);
  return { runId: run.runId, resumed: true };
}

// Arranca un run nuevo en `flowId`/`triggerNodeId` (canal ya resuelto, sin
// matching de ningún tipo -- eso es responsabilidad del caller, ver
// findMatchingTriggers para Telegram o chat_configs para el chat).
export async function startFlowRun(
  ctx: InboundContext & { flowId: string; triggerNodeId: string; data?: Record<string, unknown> },
): Promise<{ runId: string; resumed: false }> {
  const initialState = createFlowState({
    message: ctx.message,
    canal: ctx.canal,
    botId: ctx.botId,
    botName: ctx.botName ?? "",
    connectionId: ctx.connectionId ?? "",
    contactPhone: ctx.contactIdentifier,
    contactName: ctx.contactName ?? "",
    timestamp: ctx.timestamp,
    data: ctx.data ?? {},
  });
  const run = await start(runFlowWorkflow, [ctx.flowId, ctx.triggerNodeId, initialState]);
  return { runId: run.runId, resumed: false };
}

// Combina las dos mitades para el caso de UN solo flow/trigger fijo (trigger
// route, chat): reanuda si hay algo pendiente, si no arranca fresco.
export async function dispatchInbound(
  opts: InboundContext & { flowId: string; triggerNodeId: string; data?: Record<string, unknown> },
): Promise<{ runId: string; resumed: boolean }> {
  const resumed = await resumeWaitingConversation(opts);
  if (resumed) return resumed;
  return startFlowRun(opts);
}
