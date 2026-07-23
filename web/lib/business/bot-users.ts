import { and, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { botUsers, bots } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// Admin-only CRUD for the "which Google email can access which bot"
// allowlist -- Paso 1 hacia Pulpo Lite/PRO, ver web/auth.ts y
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md.

export async function listBotUsers(botId: string): Promise<string[]> {
  const db = getDb();
  const rows = await db.select({ email: botUsers.email }).from(botUsers).where(eq(botUsers.botId, botId));
  return rows.map((r) => r.email);
}

export async function addBotUser(botId: string, rawEmail: string): Promise<void> {
  const email = rawEmail.trim().toLowerCase();
  if (!email || !email.includes("@")) {
    throw new ValidationError("Email inválido");
  }
  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) throw new NotFoundError(`Bot no encontrada: ${botId}`);

  await db.insert(botUsers).values({ botId, email }).onConflictDoNothing();
}

export async function removeBotUser(botId: string, rawEmail: string): Promise<void> {
  const email = rawEmail.trim().toLowerCase();
  const db = getDb();
  await db.delete(botUsers).where(and(eq(botUsers.botId, botId), eq(botUsers.email, email)));
}

// Used by auth.ts's jwt callback -- every bot a given email is allowed into.
export async function listBotsForEmail(email: string): Promise<string[]> {
  const db = getDb();
  const rows = await db
    .select({ botId: botUsers.botId })
    .from(botUsers)
    .where(eq(botUsers.email, email.toLowerCase()));
  return rows.map((r) => r.botId);
}
