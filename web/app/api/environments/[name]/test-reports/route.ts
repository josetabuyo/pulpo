import { publishSuiteRunToEnvironment } from "@/lib/business/test-report-publish";
import { errorResponse } from "@/lib/api/errors";

// Admin-only (mismo criterio que .../sync de flows, ver
// app/api/environments/[name]/sync/route.ts -- no está en
// proxy.ts::SCOPED_BOT_ROUTES ni acepta sync-token, la sesión admin es la
// única puerta). Dispara el push server-side hacia el ambiente remoto (ver
// lib/business/test-report-publish.ts) -- el admin_token del ambiente nunca
// llega al browser.
export async function POST(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const body = await request.json();
  try {
    const result = await publishSuiteRunToEnvironment(
      name,
      String(body.bot_id ?? ""),
      body.suite_run_id ? String(body.suite_run_id) : undefined,
    );
    return Response.json(result);
  } catch (err) {
    return errorResponse(err);
  }
}
