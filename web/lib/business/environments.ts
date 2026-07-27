import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { pulpoEnvironments } from "@/lib/db/schema";
import { ConflictError, NotFoundError, ValidationError } from "@/lib/business/bots";

// CRUD de management/HANDOFF_PULPO_ENVIRONMENTS_REGISTRY.md -- registro de
// ambientes Pulpo conocidos por ESTA instancia. `admin_token` es write-only
// en la respuesta (nunca se vuelve a mostrar tras el alta, mismo criterio
// que un Secret de Vercel) -- ver lib/db/schema.ts::pulpoEnvironments para
// el porqué de guardarlo en texto plano.

type EnvironmentRow = typeof pulpoEnvironments.$inferSelect;

function toSummary(row: EnvironmentRow) {
  return {
    id: row.id,
    name: row.name,
    base_url: row.baseUrl,
    created_at: row.createdAt,
    updated_at: row.updatedAt,
  };
}

export async function listEnvironments() {
  const db = getDb();
  const rows = await db.select().from(pulpoEnvironments).orderBy(pulpoEnvironments.name);
  return rows.map(toSummary);
}

export async function addEnvironment(opts: { name: string; baseUrl: string; adminToken: string }) {
  const name = opts.name.trim();
  const baseUrl = opts.baseUrl.trim();
  const adminToken = opts.adminToken.trim();
  if (!name || !baseUrl || !adminToken) {
    throw new ValidationError("name, base_url y admin_token son requeridos");
  }
  const db = getDb();
  const [existing] = await db.select().from(pulpoEnvironments).where(eq(pulpoEnvironments.name, name));
  if (existing) throw new ConflictError(`Ya existe un ambiente con ese nombre: ${name}`);
  const id = crypto.randomUUID();
  await db.insert(pulpoEnvironments).values({ id, name, baseUrl, adminToken });
  const [row] = await db.select().from(pulpoEnvironments).where(eq(pulpoEnvironments.id, id));
  return toSummary(row);
}

// A diferencia de listEnvironments()/toSummary, SÍ incluye admin_token --
// usado por GET /api/environments/{name} (admin-only, ver proxy.ts), que el
// CLI llama para resolver `--env <name>` antes de hablarle al ambiente
// remoto. El listado plural (toSummary) es el que ve el dashboard y no
// filtra el secreto.
export async function getEnvironment(name: string) {
  const db = getDb();
  const [row] = await db.select().from(pulpoEnvironments).where(eq(pulpoEnvironments.name, name));
  if (!row) throw new NotFoundError(`Ambiente no encontrado: ${name}`);
  return { id: row.id, name: row.name, base_url: row.baseUrl, admin_token: row.adminToken };
}

export async function removeEnvironment(name: string) {
  const db = getDb();
  const [row] = await db.select().from(pulpoEnvironments).where(eq(pulpoEnvironments.name, name));
  if (!row) throw new NotFoundError(`Ambiente no encontrado: ${name}`);
  await db.delete(pulpoEnvironments).where(eq(pulpoEnvironments.name, name));
  return { ok: true };
}
