import { and, eq, sql } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots } from "@/lib/db/schema";
import { flows, flowVersions } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";
import NODE_TYPES_CATALOG from "@/lib/flow/node-types.json";

// TS port of pulpo/business/flows.py -- CRUD only (list_node_flows,
// extract-node-flow, replay, simulate, google-accounts stay Python-only for
// now, see management/HANDOFF_VERCEL_DEEP_MIGRATION.md).
//
// Output keys are snake_case on purpose -- the frontend (unmodified) reads
// flow.bot_id / flow.active / flow.contact_filter etc., same contract as
// the Python routers.

export function listNodeTypes() {
  return NODE_TYPES_CATALOG;
}

type FlowRow = typeof flows.$inferSelect;

function toSummary(row: FlowRow) {
  return {
    id: row.id,
    bot_id: row.botId,
    name: row.name,
    connection_id: row.connectionId,
    contact_phone: row.contactPhone,
    active: row.active,
    created_at: row.createdAt,
    updated_at: row.updatedAt,
    contact_filter: row.contactFilter,
    flow_kind: row.flowKind ?? "flow",
  };
}

function toFull(row: FlowRow) {
  return { ...toSummary(row), definition: row.definition ?? {} };
}

async function requireBot(botId: string) {
  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) throw new NotFoundError(`Bot '${botId}' no encontrado`);
}

export async function listFlows(botId: string) {
  await requireBot(botId);
  const db = getDb();
  const rows = await db.select().from(flows).where(eq(flows.botId, botId)).orderBy(flows.createdAt);
  return rows.map(toSummary);
}

export async function getFlow(botId: string, flowId: string) {
  const db = getDb();
  const [row] = await db.select().from(flows).where(eq(flows.id, flowId));
  if (!row || row.botId !== botId) return null;
  return toFull(row);
}

const DEFAULT_DEFINITION = { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } };

export async function createFlow(opts: {
  botId: string;
  name: string;
  definition: Record<string, unknown> | null;
  connectionId: string | null;
  contactPhone: string | null;
  contactFilter: Record<string, unknown> | null;
  flowKind: string;
}) {
  const db = getDb();
  const id = crypto.randomUUID();
  const definition = opts.definition ?? DEFAULT_DEFINITION;
  await db.insert(flows).values({
    id,
    botId: opts.botId,
    name: opts.name,
    definition,
    connectionId: opts.connectionId,
    contactPhone: opts.contactPhone,
    contactFilter: opts.contactFilter,
    flowKind: opts.flowKind,
  });
  await db.insert(flowVersions).values({ flowId: id, name: opts.name, definition });
  const [row] = await db.select().from(flows).where(eq(flows.id, id));
  return toFull(row);
}

type FlowUpdates = {
  name?: string;
  definition?: Record<string, unknown>;
  connectionId?: string | null;
  contactPhone?: string | null;
  contactFilter?: Record<string, unknown> | null;
  flowKind?: string;
  active?: boolean;
};

export async function updateFlow(botId: string, flowId: string, updates: FlowUpdates, saveVersion: boolean) {
  const db = getDb();
  const [flow] = await db.select().from(flows).where(eq(flows.id, flowId));
  if (!flow || flow.botId !== botId) return null;

  if (updates.connectionId !== undefined && !updates.connectionId) {
    throw new ValidationError(
      "connection_id no puede quedar vacío. Un flow sin conexión no dispararía para nadie.",
    );
  }

  const patch: Record<string, unknown> = { ...updates, updatedAt: new Date() };

  if (updates.definition) {
    const definition = updates.definition as { nodes?: Array<Record<string, unknown>> };
    for (const node of definition.nodes ?? []) {
      if (node.type === "message_trigger") {
        const cfg = (node.config ??= {}) as Record<string, unknown>;
        if (updates.connectionId !== undefined) cfg.connection_id = updates.connectionId;
        if (updates.contactFilter !== undefined) cfg.contact_filter = updates.contactFilter;
        break;
      }
    }
    if (saveVersion) {
      await db.insert(flowVersions).values({ flowId, name: flow.name, definition: flow.definition });
    }
  }

  await db.update(flows).set(patch).where(eq(flows.id, flowId));
  const [row] = await db.select().from(flows).where(eq(flows.id, flowId));
  return toFull(row);
}

export async function getFlowVersions(botId: string, flowId: string) {
  const db = getDb();
  const [flow] = await db.select().from(flows).where(eq(flows.id, flowId));
  if (!flow || flow.botId !== botId) return null;
  const rows = await db
    .select({ id: flowVersions.id, flowId: flowVersions.flowId, name: flowVersions.name, createdAt: flowVersions.createdAt })
    .from(flowVersions)
    .where(eq(flowVersions.flowId, flowId))
    .orderBy(sql`${flowVersions.createdAt} desc, ${flowVersions.id} desc`)
    .limit(50);
  return rows.map((r) => ({ id: r.id, flow_id: r.flowId, name: r.name, created_at: r.createdAt }));
}

export async function getFlowVersion(botId: string, flowId: string, versionId: number) {
  const db = getDb();
  const [flow] = await db.select().from(flows).where(eq(flows.id, flowId));
  if (!flow || flow.botId !== botId) return null;
  const [version] = await db.select().from(flowVersions).where(eq(flowVersions.id, versionId));
  if (!version || version.flowId !== flowId) return null;
  return {
    id: version.id,
    flow_id: version.flowId,
    name: version.name,
    definition: version.definition,
    created_at: version.createdAt,
  };
}

export async function deleteFlow(botId: string, flowId: string) {
  const db = getDb();
  const [flow] = await db.select().from(flows).where(eq(flows.id, flowId));
  if (!flow || flow.botId !== botId) return false;
  await db.delete(flowVersions).where(eq(flowVersions.flowId, flowId));
  await db.delete(flows).where(eq(flows.id, flowId));
  return true;
}

interface FlowDefinitionNode {
  type?: string;
  config?: Record<string, unknown>;
}

// TS port of compute_exit_routes (pulpo/graphs/compiler.py) -- named exit
// routes of a sub-flow, used to populate a nodo_flow node's `config.routes`
// picker in the editor. Only subflow_end nodes with a non-empty `route` are
// "named" routes; dedupe preserving first-seen order.
export function computeExitRoutes(nodes: FlowDefinitionNode[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const n of nodes) {
    if (n.type !== "subflow_end") continue;
    const route = (n.config as { route?: string } | undefined)?.route;
    if (route && !seen.has(route)) {
      seen.add(route);
      result.push(route);
    }
  }
  return result;
}

// TS port of list_node_flows (pulpo/business/flows.py) -- the bot's NodoFlow
// templates (flow_kind === "node_flow"), each with `inputs` (dynamic params
// form), `routes` (computeExitRoutes over its subflow_end nodes, populates a
// nodo_flow instance's config.routes), and `color` (definition.variables.color
// -- the editor paints nodo_flow instances with this, see
// frontend/src/store/flowStore.js::baseTypeColor()).
export async function listNodeFlows(botId: string) {
  await requireBot(botId);
  const db = getDb();
  const rows = await db.select().from(flows).where(and(eq(flows.botId, botId), eq(flows.flowKind, "node_flow")));
  return rows.map((row) => {
    const definition = (row.definition as { nodes?: FlowDefinitionNode[]; inputs?: unknown[]; variables?: { color?: string } }) ?? {};
    return {
      ...toSummary(row),
      inputs: definition.inputs ?? [],
      routes: computeExitRoutes(definition.nodes ?? []),
      color: definition.variables?.color ?? null,
    };
  });
}

export async function hasNodeType(botId: string, nodeType: string) {
  const db = getDb();
  const rows = await db.execute(sql`
    select 1 from flows
    where bot_id = ${botId}
      and definition -> 'nodes' @> ${JSON.stringify([{ type: nodeType }])}::jsonb
    limit 1
  `);
  return rows.rows.length > 0;
}
