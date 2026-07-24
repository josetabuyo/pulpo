import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline/promises";
import { neon } from "@neondatabase/serverless";
import { drizzle as drizzleNeonHttp } from "drizzle-orm/neon-http";
import { eq } from "drizzle-orm";
import { getDb } from "../lib/db/client";
import { flows, flowVersions } from "../lib/db/schema";

// Mueve la definición de UN flow entre dos ambientes equivalentes (no un
// espejo local↔prod: cada uno puede tener flows propios, este script solo
// sincroniza puntualmente el que le pidas) editando datos -- sin deploy, sin
// git. Generaliza seed-local-from-prod.ts (que clona un bot entero, de una
// sola vez, para bootstrapear un ambiente nuevo) al caso de uso del día a
// día: iterar un flow en local (contra `next dev`, Local World, cero cuota
// -- ver management/HANDOFF_WORKFLOW_LOCAL_DEV.md) y una vez conforme,
// "pushearlo" -- entendido como mover sus datos, no como git push -- al otro
// ambiente.
//
// `pull`: copia la definición del flow desde REMOTE_DATABASE_URL hacia acá
//         (DATABASE_URL, típicamente local). Sin riesgo, para empezar a
//         iterar sobre la versión más nueva.
// `push`: copia la definición de acá hacia REMOTE_DATABASE_URL. Pisa datos
//         reales del otro ambiente -- SIEMPRE muestra el diff y pide
//         confirmación explícita (salvo --yes), y guarda la definición
//         previa del destino como flow_version antes de pisarla (mismo
//         mecanismo de "undo" que updateFlow(..., saveVersion=true) en
//         lib/business/flows.ts).
//
// Uso:
//   REMOTE_DATABASE_URL=<neon-url> npx dotenv -e .env.local -- \
//     tsx scripts/sync-flow.ts --direction pull --bot luganense --flow 0019d8f2-ada5-4409-99bf-50921beb875b
//
//   REMOTE_DATABASE_URL=<neon-url> npx dotenv -e .env.local -- \
//     tsx scripts/sync-flow.ts --direction push --bot luganense --flow 0019d8f2-ada5-4409-99bf-50921beb875b

export function arg(name: string, required = true): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1 || !process.argv[i + 1]) {
    if (required) throw new Error(`falta --${name}`);
    return undefined;
  }
  return process.argv[i + 1];
}

export function parseDirection(value: string | undefined): "pull" | "push" {
  if (value !== "pull" && value !== "push") {
    throw new Error(`--direction inválido: ${JSON.stringify(value)} (esperado "pull" o "push")`);
  }
  return value;
}

type FlowRow = typeof flows.$inferSelect;
type RemoteDb = ReturnType<typeof drizzleNeonHttp>;

async function readFlow(db: RemoteDb | ReturnType<typeof getDb>, botId: string, flowId: string): Promise<FlowRow> {
  const [row] = await db.select().from(flows).where(eq(flows.id, flowId));
  if (!row || row.botId !== botId) {
    throw new Error(`flow ${flowId} no encontrado para bot ${botId} en este ambiente`);
  }
  return row;
}

function printDiff(label: string, before: unknown, after: unknown) {
  const dir = mkdtempSync(join(tmpdir(), "sync-flow-"));
  const beforePath = join(dir, "before.json");
  const afterPath = join(dir, "after.json");
  writeFileSync(beforePath, JSON.stringify(before, null, 2) + "\n");
  writeFileSync(afterPath, JSON.stringify(after, null, 2) + "\n");
  console.log(`\n--- diff (destino actual vs lo que se va a escribir) — ${label} ---`);
  try {
    execFileSync("diff", ["-u", beforePath, afterPath], { stdio: "inherit" });
    console.log("(sin diferencias)");
  } catch (e) {
    // diff sale con exit code 1 cuando encuentra diferencias -- no es un error real.
    if ((e as { status?: number }).status !== 1) throw e;
  }
  console.log("");
}

async function confirm(question: string): Promise<boolean> {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer = await rl.question(`${question} [y/N] `);
  rl.close();
  return answer.trim().toLowerCase() === "y";
}

async function main() {
  const direction = parseDirection(arg("direction"));
  const botId = arg("bot")!;
  const flowId = arg("flow")!;
  const skipConfirm = process.argv.includes("--yes");

  const remoteUrl = process.env.REMOTE_DATABASE_URL;
  if (!remoteUrl) throw new Error("Seteá REMOTE_DATABASE_URL (Postgres del otro ambiente)");

  const localDb = getDb();
  const remoteDb = drizzleNeonHttp(neon(remoteUrl));

  const [sourceDb, targetDb] = direction === "pull" ? [remoteDb, localDb] : [localDb, remoteDb];

  const sourceFlow = await readFlow(sourceDb, botId, flowId);
  const targetFlow = await readFlow(targetDb, botId, flowId);

  printDiff(`${direction} · ${botId}/${flowId}`, targetFlow.definition, sourceFlow.definition);

  if (JSON.stringify(targetFlow.definition) === JSON.stringify(sourceFlow.definition)) {
    console.log("El destino ya tiene esta misma definición -- nada para sincronizar.");
    return;
  }

  if (!skipConfirm && !(await confirm(`¿Escribir esta definición en el destino (${direction})?`))) {
    console.log("Cancelado -- no se escribió nada.");
    return;
  }

  // Guarda la definición ACTUAL del destino como flow_version antes de
  // pisarla -- mismo patrón que updateFlow(..., saveVersion=true).
  await targetDb.insert(flowVersions).values({
    flowId: targetFlow.id,
    name: targetFlow.name,
    definition: targetFlow.definition,
  });
  await targetDb
    .update(flows)
    .set({ definition: sourceFlow.definition, name: sourceFlow.name, updatedAt: new Date() })
    .where(eq(flows.id, flowId));

  console.log(`Listo: ${direction} de ${botId}/${flowId} aplicado. Versión previa del destino guardada en flow_versions.`);
}

if (process.argv[1]?.endsWith("sync-flow.ts")) {
  main().then(() => process.exit(0));
}
