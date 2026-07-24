import { getFlowVersions } from "@/lib/business/flows";

// TS port of pulpo/interfaces/api/routers/flows.py (GET ".../versions").
export async function GET(_request: Request, { params }: { params: Promise<{ botId: string; flowId: string }> }) {
  const { botId, flowId } = await params;
  const versions = await getFlowVersions(botId, flowId);
  if (versions === null) return Response.json({ detail: "Flow no encontrado" }, { status: 404 });
  return Response.json(versions);
}
