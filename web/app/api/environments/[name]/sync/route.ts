import { applyEnvironmentFlowSync, parseSyncDirection } from "@/lib/business/environment-sync";
import { errorResponse } from "@/lib/api/errors";

// Admin-only, igual que .../diff -- ESTA sí escribe: pull actualiza el flow
// local, push actualiza el flow remoto (siempre active:false en el destino,
// ver lib/business/environment-sync.ts).
export async function POST(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const body = await request.json();
  try {
    const result = await applyEnvironmentFlowSync(
      name,
      String(body.bot_id ?? ""),
      String(body.flow_id ?? ""),
      parseSyncDirection(body.direction),
    );
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
