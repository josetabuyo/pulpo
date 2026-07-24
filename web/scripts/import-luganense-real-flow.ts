import { readFileSync } from "node:fs";
import { getDb } from "../lib/db/client";
import { flows } from "../lib/db/schema";

// One-off: import the REAL luganense flow ("Orquestador Vendedor Mejorado")
// and its 3 node_flow templates (get_data, confirm_choice, reply_and_close)
// verbatim from the Python side's SQLite (source of truth for flow
// definitions today) into Neon, so the new webhook serves the real business
// logic instead of the throwaway test flow (see
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md, "Telegram vía webhook").
// The export itself (data/messages.db -> JSON) runs via `python3`, since
// there's no sqlite driver in web/'s node_modules -- see the sibling
// export step documented in the handoff.
const EXPORT_JSON = process.env.LUGANENSE_FLOWS_EXPORT_JSON || "";

interface ExportedFlow {
  id: string;
  bot_id: string;
  name: string;
  definition: { nodes?: unknown[]; edges?: unknown[] };
  connection_id: string | null;
  contact_phone: string | null;
  active: boolean;
  flow_kind: string | null;
  contact_filter: Record<string, unknown> | null;
}

async function main() {
  if (!EXPORT_JSON) throw new Error("LUGANENSE_FLOWS_EXPORT_JSON no seteado (path al JSON exportado de la SQLite de Python)");
  const rows: ExportedFlow[] = JSON.parse(readFileSync(EXPORT_JSON, "utf-8"));
  const db = getDb();

  for (const row of rows) {
    await db
      .insert(flows)
      .values({
        id: row.id,
        botId: row.bot_id,
        name: row.name,
        definition: row.definition,
        connectionId: row.connection_id,
        contactPhone: row.contact_phone,
        active: row.active,
        contactFilter: row.contact_filter,
        flowKind: row.flow_kind || "flow",
      })
      .onConflictDoUpdate({
        target: flows.id,
        set: {
          name: row.name,
          definition: row.definition,
          connectionId: row.connection_id,
          active: row.active,
          contactFilter: row.contact_filter,
          flowKind: row.flow_kind || "flow",
        },
      });
    console.log(`Importado: ${row.id} (${row.name})`);
  }
}

main().then(() => process.exit(0));
