import { deleteConnection } from "@/lib/business/connections";

// TS port of pulpo/interfaces/api/routers/connections.py (DELETE "/{number}").
export async function DELETE(_request: Request, { params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const found = await deleteConnection(number);
  if (!found) return Response.json({ detail: `Número no encontrado: ${number}` }, { status: 404 });
  return Response.json({ ok: true });
}
