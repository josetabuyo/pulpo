import { listBots, createBot } from "@/lib/business/bots";
import { errorResponse } from "@/lib/api/errors";

// TS port of pulpo/interfaces/api/routers/bots.py (GET/POST "").
export async function GET() {
  return Response.json(await listBots());
}

export async function POST(request: Request) {
  const body = await request.json();
  const id = String(body.id ?? "");
  const name = String(body.name ?? "");
  const password = String(body.password ?? "");
  if (!id.trim() || !name.trim() || !password.trim()) {
    return Response.json({ detail: "id, name y password son requeridos" }, { status: 400 });
  }
  try {
    const result = await createBot(id, name, password);
    return Response.json(result, { status: 201 });
  } catch (err) {
    return errorResponse(err);
  }
}
