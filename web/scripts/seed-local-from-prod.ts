// One-off script (2026-07-22): copia el bot `luganense` (nombre + flows +
// flow_versions) desde Neon producción a la Postgres local de dev, con el
// nombre cambiado a "Luganense Local" para no confundirla en el dashboard,
// y SIN copiar telegram_connections -- queda sin token asignado a
// propósito, lista para asignar uno de prueba más adelante sin arriesgar
// mandar mensajes reales por accidente. No se corre en CI ni en build, es
// un utility de una sola vez -- no falla si ya existe (upsert).
//
// Uso: PROD_DATABASE_URL=<url de Neon> npx dotenv -e .env.local -- tsx scripts/seed-local-from-prod.ts
import { neon } from "@neondatabase/serverless";
import { drizzle as drizzleNeonHttp } from "drizzle-orm/neon-http";
import { eq } from "drizzle-orm";
import { getDb } from "../lib/db/client";
import { bots, flows, flowVersions } from "../lib/db/schema";

const SOURCE_BOT_ID = "luganense";
const LOCAL_NAME = "Luganense Local";

async function main() {
  const prodUrl = process.env.PROD_DATABASE_URL;
  if (!prodUrl) throw new Error("Seteá PROD_DATABASE_URL (la de Neon producción) para leer desde ahí.");

  const prodDb = drizzleNeonHttp(neon(prodUrl));
  const localDb = getDb();

  const [bot] = await prodDb.select().from(bots).where(eq(bots.id, SOURCE_BOT_ID));
  if (!bot) throw new Error(`No se encontró el bot '${SOURCE_BOT_ID}' en producción`);

  const prodFlows = await prodDb.select().from(flows).where(eq(flows.botId, SOURCE_BOT_ID));
  const prodVersions = await prodDb
    .select()
    .from(flowVersions)
    .where(eq(flowVersions.flowId, prodFlows[0]?.id ?? "__none__"));

  await localDb
    .insert(bots)
    .values({ id: bot.id, name: LOCAL_NAME, password: "local-dev-unused" })
    .onConflictDoUpdate({ target: bots.id, set: { name: LOCAL_NAME } });

  for (const flow of prodFlows) {
    await localDb
      .insert(flows)
      .values(flow)
      .onConflictDoUpdate({ target: flows.id, set: { definition: flow.definition, name: flow.name } });
  }

  for (const version of prodVersions) {
    const { id, ...rest } = version;
    await localDb.insert(flowVersions).values(rest);
  }

  console.log(
    `Listo: '${LOCAL_NAME}' (id=${bot.id}) con ${prodFlows.length} flow(s) copiados a la DB local. ` +
      `Sin token de Telegram -- asignalo desde el tab "Conexiones" cuando quieras probarlo.`
  );
}

main().then(() => process.exit(0)).catch((err) => {
  console.error(err);
  process.exit(1);
});
