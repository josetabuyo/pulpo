import { listEnvironments, addEnvironment } from "@/lib/business/environments";
import { errorResponse } from "@/lib/api/errors";

// Registro de ambientes Pulpo (management/HANDOFF_PULPO_ENVIRONMENTS_REGISTRY.md).
// Admin-only -- no está en proxy.ts::SCOPED_BOT_ROUTES ni acepta sync-token,
// a propósito: gestionar A QUÉ ambientes habla esta instancia es una
// decisión de quien administra el dashboard, no de un bot_user ni de otro
// ambiente remoto.
export async function GET() {
  return Response.json(await listEnvironments());
}

export async function POST(request: Request) {
  const body = await request.json();
  try {
    const env = await addEnvironment({
      name: String(body.name ?? ""),
      baseUrl: String(body.base_url ?? ""),
      adminToken: String(body.admin_token ?? ""),
    });
    return Response.json(env, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
