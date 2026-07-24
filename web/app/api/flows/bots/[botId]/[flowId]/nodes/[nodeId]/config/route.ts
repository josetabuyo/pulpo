import { setFlowNodeConfig } from "@/lib/business/flows";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// PATCH liviano del config de UN nodo (tab "Triggers", 2026-07-23): el
// toggle "Pausar" manda solo `{...configActual, paused}`, el modal
// "Configurar" manda el config completo reemplazado. No reabre/reescribe el
// editor de flow, no guarda flow_versions (ajuste de config, no edición
// estructural).
export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ botId: string; flowId: string; nodeId: string }> },
) {
  const { botId, flowId, nodeId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  const body = await request.json().catch(() => ({}));
  const config = (body.config ?? {}) as Record<string, unknown>;
  try {
    return Response.json(await setFlowNodeConfig(botId, flowId, nodeId, config));
  } catch (err) {
    return errorResponse(err);
  }
}
