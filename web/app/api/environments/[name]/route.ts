import { getEnvironment, removeEnvironment } from "@/lib/business/environments";
import { errorResponse } from "@/lib/api/errors";

// Único lugar donde admin_token viaja en una respuesta -- lo usa el CLI para
// resolver `--env <name>` antes de llamar al ambiente remoto (ver
// cli/main.ts::resolveEnvironment). Admin-only, igual que el resto de esta
// ruta (no está en proxy.ts::SCOPED_BOT_ROUTES ni acepta sync-token).
export async function GET(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  try {
    return Response.json(await getEnvironment(name));
  } catch (err) {
    return errorResponse(err);
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  try {
    return Response.json(await removeEnvironment(name));
  } catch (err) {
    return errorResponse(err);
  }
}
