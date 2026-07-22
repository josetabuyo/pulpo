import { getFlowVersion } from "@/lib/business/flows";

// TS port of pulpo/interfaces/api/routers/flows.py (GET ".../versions/{version_id}").
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ botId: string; flowId: string; versionId: string }> },
) {
  const { botId, flowId, versionId } = await params;
  const version = await getFlowVersion(botId, flowId, Number(versionId));
  if (!version) return Response.json({ detail: "Versión no encontrada" }, { status: 404 });
  return Response.json(version);
}
