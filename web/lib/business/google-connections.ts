import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { googleConnections } from "@/lib/db/schema";
import { ValidationError, NotFoundError } from "@/lib/business/bots";

// TS port of pulpo/business/connections_google.py.

export class PermissionDeniedError extends Error {}

export async function listGoogleConnections(botId: string) {
  const db = getDb();
  return db.select().from(googleConnections).where(eq(googleConnections.botId, botId));
}

export async function createGoogleConnection(botId: string, credentialsJson: string, label: string | null | undefined) {
  let info: Record<string, unknown>;
  try {
    info = JSON.parse(credentialsJson);
  } catch {
    throw new ValidationError("credentials_json no es JSON válido");
  }
  const email = typeof info.client_email === "string" ? info.client_email : "";
  if (!email || !("private_key" in info)) {
    throw new ValidationError("El JSON debe tener client_email y private_key");
  }
  const id = crypto.randomUUID();
  const resolvedLabel = label || email.split("@")[0];

  const db = getDb();
  await db.insert(googleConnections).values({
    id,
    botId,
    credentialsJson,
    email,
    label: resolvedLabel,
  });
  return { ok: true, id, email, label: resolvedLabel };
}

export async function deleteGoogleConnection(botId: string, connId: string) {
  if (connId === "pulpo-default") {
    throw new PermissionDeniedError("La conexión Pulpo no se puede eliminar");
  }
  const db = getDb();
  const [conn] = await db.select().from(googleConnections).where(eq(googleConnections.id, connId));
  if (!conn || conn.botId !== botId) {
    throw new NotFoundError(`Conexión no encontrada para esta bot: ${connId}`);
  }
  await db.delete(googleConnections).where(eq(googleConnections.id, connId));
  return true;
}
