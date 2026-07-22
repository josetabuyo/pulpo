import { patchConnectionSettings } from "@/lib/business/connections";

// TS port of pulpo/interfaces/api/routers/connections.py (PATCH "/{number}/settings").
export async function PATCH(request: Request, { params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const body = await request.json();
  const ok = await patchConnectionSettings(number, Boolean(body.allow_mass));
  if (!ok) return Response.json({ detail: `Número no encontrado: ${number}` }, { status: 404 });
  return Response.json({ ok: true, allow_mass: Boolean(body.allow_mass) });
}
