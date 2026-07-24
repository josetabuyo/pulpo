import { getConnectionFilter, setConnectionFilter } from "@/lib/business/connections";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/connections.py (GET/PUT/DELETE "/{number}/filter-config").
export async function GET(_request: Request, { params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  try {
    return Response.json(await getConnectionFilter(number));
  } catch (err) {
    return errorResponse(err);
  }
}

export async function PUT(request: Request, { params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const body = await request.json();
  const filter = {
    include_all_known: Boolean(body.include_all_known),
    include_unknown: Boolean(body.include_unknown),
    included: Array.isArray(body.included) ? body.included : [],
    excluded: Array.isArray(body.excluded) ? body.excluded : [],
  };
  const ok = await setConnectionFilter(number, filter);
  if (!ok) return Response.json({ detail: "Número no encontrado" }, { status: 404 });
  return Response.json({ ok: true, filter });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const ok = await setConnectionFilter(number, null);
  if (!ok) return Response.json({ detail: "Número no encontrado" }, { status: 404 });
  return Response.json({ ok: true });
}
