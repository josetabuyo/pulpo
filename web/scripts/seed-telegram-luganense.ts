import { readFileSync } from "node:fs";
import { getDb } from "../lib/db/client";
import { bots, flows, telegramConnections } from "../lib/db/schema";

// One-off seed to validate the real Telegram webhook path against the
// luganense bot (see management/HANDOFF_VERCEL_DEEP_MIGRATION.md). Reads the
// real token from the Python side's connections.json (source of truth for
// bot config today) so it's never typed into a prompt or printed here.
const CONNECTIONS_JSON = "/Users/josetabuyo/Development/pulpo/_/connections.json";

async function main() {
  const config = JSON.parse(readFileSync(CONNECTIONS_JSON, "utf-8"));
  const bot = config.bots.find((b: { id: string }) => b.id === "luganense");
  if (!bot) throw new Error("bot 'luganense' no encontrada en connections.json");
  const tg = bot.telegram?.[0];
  if (!tg) throw new Error("bot 'luganense' no tiene conexión de telegram en connections.json");

  const tokenId = String(tg.token).split(":")[0];
  const token = String(tg.token);
  const allowMass = Boolean(tg.allow_mass);

  const db = getDb();

  await db
    .insert(bots)
    .values({ id: bot.id, name: bot.name, password: crypto.randomUUID() })
    .onConflictDoNothing();

  await db
    .insert(telegramConnections)
    .values({ tokenId, botId: bot.id, token, allowMass })
    .onConflictDoUpdate({ target: telegramConnections.tokenId, set: { token, allowMass, botId: bot.id } });

  const definition = {
    nodes: [
      {
        id: "trigger1",
        type: "telegram_trigger",
        config: { connection_id: tokenId, contact_filter: null, message_pattern: "", cooldown_hours: 0 },
      },
      {
        id: "reply1",
        type: "send_message",
        config: {
          to: "",
          message:
            "Pulpo (Vercel) te saluda, {{contact_name}}. Esto es un test de validación del webhook de Telegram vía Next.js + Workflow DevKit.",
        },
      },
    ],
    edges: [{ source: "trigger1", target: "reply1", label: null }],
  };

  await db
    .insert(flows)
    .values({
      id: "luganense-telegram-webhook-test",
      botId: bot.id,
      name: "TEST webhook Telegram (borrar tras validar)",
      active: true,
      flowKind: "flow",
      connectionId: tokenId,
      definition,
    })
    .onConflictDoUpdate({
      target: flows.id,
      set: { definition, active: true, connectionId: tokenId },
    });

  console.log(`Listo. tokenId=${tokenId}, allowMass=${allowMass}. NO se imprime el token completo.`);
}

main().then(() => process.exit(0));
