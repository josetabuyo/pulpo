import { diffEnvironmentFlow, parseSyncDirection } from "@/lib/business/environment-sync";
import { errorResponse } from "@/lib/api/errors";

// Admin-only (no está en proxy.ts::SCOPED_BOT_ROUTES ni acepta sync-token) --
// usado por el botón "Sync" del editor de flows para mostrar el diff antes
// de confirmar. Solo lectura, no escribe nada.
export async function POST(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const body = await request.json();
  try {
    const result = await diffEnvironmentFlow(
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
