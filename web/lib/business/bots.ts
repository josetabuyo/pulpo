import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots, phoneConnections, telegramConnections } from "@/lib/db/schema";
import { getTelegramBotInfo } from "@/lib/business/telegram";

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
        username: t.username || "",
        botName: t.botName || "",
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

// TS port of pulpo/interfaces/ui/routers/bot_portal.py::bot_add_telegram --
// scoped to the config write, no live client to start (see module docstring).
// Unlike the Python original (which never calls getMe and only discovers a
// bad token when it tries to start the polling client), this validates the
// token against the real Telegram API up front -- there's no later attempt
// that would otherwise catch it.
export async function addTelegramConnection(botId: string, rawToken: string) {
  const token = rawToken.trim();
  if (!token || !token.includes(":")) {
    throw new ValidationError("Token inválido (formato: 123456789:ABC...)");
  }
  const tokenId = token.split(":")[0];
  const db = getDb();

  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) throw new NotFoundError(`Bot no encontrada: ${botId}`);

  const [existing] = await db
    .select()
    .from(telegramConnections)
    .where(eq(telegramConnections.tokenId, tokenId));
  if (existing) throw new ConflictError("Ese token ya está configurado");

  let username = "";
  let botName = "";
  try {
    ({ username, botName } = await getTelegramBotInfo(token));
  } catch (err) {
    throw new ValidationError(
      `No se pudo validar el token contra Telegram: ${err instanceof Error ? err.message : err}`,
    );
  }

  await db.insert(telegramConnections).values({ tokenId, botId, token, username, botName });
  return { ok: true, session_id: `${botId}-tg-${tokenId}`, username, bot_name: botName };
}

export async function deleteTelegramConnection(botId: string, tokenId: string) {
  const db = getDb();
  const [conn] = await db
    .select()
    .from(telegramConnections)
    .where(eq(telegramConnections.tokenId, tokenId));
  if (!conn || conn.botId !== botId) {
    throw new NotFoundError(`Conexión Telegram no encontrada: ${tokenId}`);
  }
  await db.delete(telegramConnections).where(eq(telegramConnections.tokenId, tokenId));
  return { ok: true };
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
