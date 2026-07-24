import { listNodeFlows } from "../lib/business/flows";

// One-off check: confirm listNodeFlows() returns color/routes/inputs
// correctly for luganense's 3 NodoFlow templates (get_data, confirm_choice,
// reply_and_close) -- see management/HANDOFF_VERCEL_DEEP_MIGRATION.md.
async function main() {
  const result = await listNodeFlows("luganense");
  console.log(JSON.stringify(result.map((r) => ({ id: r.id, name: r.name, color: r.color, routes: r.routes, inputs: r.inputs.length })), null, 2));
}

main().then(() => process.exit(0));
