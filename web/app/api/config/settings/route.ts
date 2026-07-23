import { getSettings, updateSettings } from "@/lib/business/settings";

// TS port of pulpo/interfaces/api/routers/settings.py (GET/PUT "/config/settings").
export async function GET() {
  return Response.json(await getSettings());
}

export async function PUT(request: Request) {
  const body = await request.json();
  const patch: { wa_poll_interval_seconds?: number } = {};
  if (body.wa_poll_interval_seconds != null) {
    patch.wa_poll_interval_seconds = Number(body.wa_poll_interval_seconds);
  }
  return Response.json(await updateSettings(patch));
}
