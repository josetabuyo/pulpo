import { eq } from "drizzle-orm";
import { getDb } from "../lib/db/client";
import { flows } from "../lib/db/schema";

// One-off (2026-07-22, user request): luganense's real telegram_trigger
// should have no contact_filter and no cooldown in production -- clears
// both on the live flow's definition so any contact (known or not) can
// trigger it, and repeated messages aren't rate-limited.
const FLOW_ID = "0019d8f2-ada5-4409-99bf-50921beb875b";

interface FlowNode {
  id: string;
  type: string;
  config?: Record<string, unknown>;
}

async function main() {
  const db = getDb();
  const [flow] = await db.select().from(flows).where(eq(flows.id, FLOW_ID));
  if (!flow) throw new Error(`flow ${FLOW_ID} no encontrado`);

  const definition = flow.definition as { nodes: FlowNode[]; edges: unknown[] };
  const trigger = definition.nodes.find((n) => n.type === "telegram_trigger");
  if (!trigger) throw new Error("telegram_trigger no encontrado en el flow");

  trigger.config = { ...(trigger.config ?? {}), contact_filter: null, cooldown_hours: 0 };

  await db.update(flows).set({ definition }).where(eq(flows.id, FLOW_ID));
  console.log("Listo. telegram_trigger.config:", JSON.stringify(trigger.config));
}

main().then(() => process.exit(0));
