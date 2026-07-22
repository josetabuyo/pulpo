import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots, phoneConnections, telegramConnections } from "@/lib/db/schema";

// TS port of pulpo/business/bots.py -- config-only (no live process status,
// see management/HANDOFF_VERCEL_DEEP_MIGRATION.md: WhatsApp/Telegram daemons
// only run locally). Every connection is reported "stopped" instead of
// querying wavi_status / in-memory clients, which don't exist here.

export async function listBots() {
  const db = getDb();
  const [botRows, phoneRows, tgRows] = await Promise.all([
    db.select().from(bots),
    db.select().from(phoneConnections),
    db.select().from(telegramConnections),
  ]);

  return botRows.map((bot) => ({
    id: bot.id,
    name: bot.name,
    phones: phoneRows
      .filter((p) => p.botId === bot.id)
      .map((p) => ({
        number: p.number,
        alias: p.alias || "",
        sessionId: p.number,
        status: "stopped",
        allowMass: p.allowMass,
      })),
    telegram: tgRows
      .filter((t) => t.botId === bot.id)
      .map((t) => ({
        tokenId: t.tokenId,
        sessionId: `${bot.id}-tg-${t.tokenId}`,
        status: "stopped",
        username: "",
        botName: "",
        allowMass: t.allowMass,
      })),
  }));
}

export async function createBot(id: string, name: string, password: string) {
  if (!id.trim() || !name.trim() || !password.trim()) {
    throw new ValidationError("id, name y password son requeridos");
  }
  const db = getDb();
  const [existing] = await db.select().from(bots).where(eq(bots.id, id));
  if (existing) throw new ConflictError(`Ya existe una bot con ese id: ${id}`);
  await db.insert(bots).values({ id, name, password });
  return { ok: true, id };
}

export async function updateBot(botId: string, name: string | null | undefined) {
  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) return false;
  if (name) {
    await db.update(bots).set({ name, updatedAt: new Date() }).where(eq(bots.id, botId));
  }
  return true;
}

export async function deleteBot(botId: string) {
  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) return false;
  await db.delete(phoneConnections).where(eq(phoneConnections.botId, botId));
  await db.delete(telegramConnections).where(eq(telegramConnections.botId, botId));
  await db.delete(bots).where(eq(bots.id, botId));
  return true;
}

export async function patchTelegramSettings(botId: string, tokenId: string, allowMass: boolean) {
  const db = getDb();
  const [conn] = await db
    .select()
    .from(telegramConnections)
    .where(eq(telegramConnections.tokenId, tokenId));
  if (!conn || conn.botId !== botId) {
    throw new NotFoundError(`Conexión Telegram no encontrada: ${tokenId}`);
  }
  await db
    .update(telegramConnections)
    .set({ allowMass })
    .where(eq(telegramConnections.tokenId, tokenId));
  return { ok: true, allow_mass: allowMass };
}

export class ValidationError extends Error {}
export class ConflictError extends Error {}
export class NotFoundError extends Error {}
