import { listNodeTypes } from "@/lib/business/flows";

// TS port of pulpo/interfaces/api/routers/flows.py (GET /node-types).
// Catalog is a static snapshot (web/lib/flow/node-types.json) dumped from
// pulpo.business.flows.list_node_types() -- see handoff doc for how to
// regenerate it after adding/changing a node type in Python.
export async function GET() {
  return Response.json(listNodeTypes());
}
