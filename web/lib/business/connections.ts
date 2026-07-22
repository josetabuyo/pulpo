import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots, phoneConnections } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// TS port of pulpo/business/connections_phones.py -- config-only, see
// lib/business/bots.ts for why status is always "stopped".

export async function listConnections() {
  const db = getDb();
  const [botRows, phoneRows] = await Promise.all([
    db.select().from(bots),
    db.select().from(phoneConnections),
  ]);
  const botById = new Map(botRows.map((b) => [b.id, b]));

  return phoneRows.map((p) => ({
    botId: p.botId,
    botName: botById.get(p.botId)?.name ?? "",
    number: p.number,
    sessionId: p.number,
    status: "stopped",
  }));
}

export async function createConnection(botId: string, number: string, botName: string | null | undefined) {
  if (!botId || !number) throw new ValidationError("botId y number son requeridos");
  const db = getDb();

  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) {
    if (!botName) throw new ValidationError("Bot nueva requiere botName");
    await db.insert(bots).values({ id: botId, name: botName, password: crypto.randomUUID() });
  }

  const [existingPhone] = await db.select().from(phoneConnections).where(eq(phoneConnections.number, number));
  if (existingPhone) throw new ValidationError("El número ya está en esta bot.");

  await db.insert(phoneConnections).values({ number, botId });
  return { ok: true, sessionId: number };
}

export async function deleteConnection(number: string) {
  const db = getDb();
  const [phone] = await db.select().from(phoneConnections).where(eq(phoneConnections.number, number));
  if (!phone) return false;
  await db.delete(phoneConnections).where(eq(phoneConnections.number, number));
  return true;
}

export async function patchConnectionSettings(number: string, allowMass: boolean) {
  const db = getDb();
  const [phone] = await db.select().from(phoneConnections).where(eq(phoneConnections.number, number));
  if (!phone) return false;
  await db.update(phoneConnections).set({ allowMass }).where(eq(phoneConnections.number, number));
  return true;
}

export async function moveConnection(number: string, targetBotId: string) {
  if (!targetBotId) throw new ValidationError("targetBotId requerido");
  const db = getDb();

  const [targetBot] = await db.select().from(bots).where(eq(bots.id, targetBotId));
  if (!targetBot) throw new NotFoundError(`Bot destino no encontrada: ${targetBotId}`);

  const [phone] = await db.select().from(phoneConnections).where(eq(phoneConnections.number, number));
  if (!phone) throw new NotFoundError(`Número no encontrado: ${number}`);
  if (phone.botId === targetBotId) throw new ValidationError("El teléfono ya está en esa bot");

  const fromBotId = phone.botId;
  await db.update(phoneConnections).set({ botId: targetBotId }).where(eq(phoneConnections.number, number));
  return { ok: true, from: fromBotId, to: targetBotId };
}

const EMPTY_FILTER = { include_all_known: false, include_unknown: false, included: [], excluded: [] };

export async function getConnectionFilter(number: string) {
  const db = getDb();
  const [phone] = await db.select().from(phoneConnections).where(eq(phoneConnections.number, number));
  if (!phone) throw new NotFoundError(`Número no encontrado: ${number}`);
  return phone.defaultFilter ?? EMPTY_FILTER;
}

export async function setConnectionFilter(number: string, filter: unknown) {
  const db = getDb();
  const [phone] = await db.select().from(phoneConnections).where(eq(phoneConnections.number, number));
  if (!phone) return false;
  await db.update(phoneConnections).set({ defaultFilter: filter }).where(eq(phoneConnections.number, number));
  return true;
}
