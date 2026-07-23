import { and, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flowRunSteps, flowRuns, flows, gateWaits } from "@/lib/db/schema";
import { NODE_REGISTRY } from "@/lib/nodes/registry";
import type { FlowState } from "@/lib/nodes/state";
import type { FlowNodeDef, FlowEdgeDef } from "./graph";

// Steps have full Node.js access (DB clients, fetch, etc.) -- see
// node_modules/workflow/docs/foundations/workflows-and-steps.mdx. The
// orchestrating "use workflow" function in workflows/run-flow.ts stays pure
// and only calls these.

export async function loadFlow(flowId: string) {
  "use step";
  const [flow] = await getDb().select().from(flows).where(eq(flows.id, flowId));
  if (!flow) throw new Error(`flow ${flowId} not found`);
  if (!flow.active) throw new Error(`flow ${flowId} is not active`);
  const definition = flow.definition as { nodes: FlowNodeDef[]; edges: FlowEdgeDef[] };
  return { botId: flow.botId, connectionId: flow.connectionId, nodes: definition.nodes, edges: definition.edges };
}

export async function startFlowRun(params: {
  runId: string;
  flowId: string;
  botId: string;
  connectionId: string | null;
  contactPhone: string | null;
  triggerData: unknown;
  workflowRunId: string;
}) {
  "use step";
  await getDb().insert(flowRuns).values({
    runId: params.runId,
    flowId: params.flowId,
    botId: params.botId,
    connectionId: params.connectionId,
    contactPhone: params.contactPhone,
    status: "running",
    triggerData: params.triggerData,
    workflowRunId: params.workflowRunId,
  });
}

export async function endFlowRun(runId: string, status: string) {
  "use step";
  await getDb().update(flowRuns).set({ status, endedAt: new Date() }).where(eq(flowRuns.runId, runId));
}

// Loads a sub-flow's raw definition for expand_node_flows (nodo_flow lookup)
// -- separate from loadFlow() because subflows aren't validated as "the"
// flow being run (no active check, no botId/connectionId needed).
export async function fetchFlowDefinition(flowId: string) {
  "use step";
  const [flow] = await getDb().select().from(flows).where(eq(flows.id, flowId));
  if (!flow) return null;
  const definition = flow.definition as { nodes?: FlowNodeDef[]; edges?: FlowEdgeDef[] };
  return { nodes: definition.nodes ?? [], edges: definition.edges ?? [] };
}

// Persists a wait_user pause (TS port of the DB half of pulpo/graphs/
// compiler.py's wait_user handling in _run_bfs -- Python's
// db.set_wait_user_info). resumeNodeId/slotsJson let a later Telegram
// message resume this exact run from where it paused, see
// app/api/telegram/webhook/[tokenId]/route.ts.
export async function markWaitingGate(params: { runId: string; resumeNodeId: string; slotsJson: Record<string, unknown> }) {
  "use step";
  await getDb()
    .update(flowRuns)
    .set({ status: "waiting_gate", resumeNodeId: params.resumeNodeId, slotsJson: params.slotsJson })
    .where(eq(flowRuns.runId, params.runId));
}

// TS port of GateNode's storage half (pulpo/graphs/nodes/gate.py's
// _GATE_STORE/_store_waiting_run/_pop_waiting_run), moved from in-process
// dicts to the gate_waits table since Vercel has no long-lived process. Each
// call appends `message` for (nodeId, contactPhone) and reports whether the
// gate just opened (accumulated length reached waitFor). See gateWaits in
// lib/db/schema.ts for the one-slot waitingRunId caveat.
export async function accumulateGate(params: {
  nodeId: string;
  contactPhone: string;
  message: string;
  waitFor: number;
  runId: string;
}): Promise<{ opened: boolean; messages: string[]; previousWaitingRunId: string | null }> {
  "use step";
  const db = getDb();
  const where = and(eq(gateWaits.nodeId, params.nodeId), eq(gateWaits.contactPhone, params.contactPhone));
  const [existing] = await db.select().from(gateWaits).where(where);
  const messages = [...((existing?.messages as string[] | undefined) ?? []), params.message];

  if (messages.length < params.waitFor) {
    if (existing) {
      await db.update(gateWaits).set({ messages, waitingRunId: params.runId, updatedAt: new Date() }).where(where);
    } else {
      await db.insert(gateWaits).values({ nodeId: params.nodeId, contactPhone: params.contactPhone, messages, waitingRunId: params.runId });
    }
    return { opened: false, messages, previousWaitingRunId: null };
  }

  const previousWaitingRunId = existing?.waitingRunId ?? null;
  await db.delete(gateWaits).where(where);
  return { opened: true, messages, previousWaitingRunId };
}

export async function logFlowStep(params: {
  runId: string;
  nodeId: string;
  nodeType: string;
  inputState: unknown;
  outputState: unknown;
  status: "ok" | "error" | "blocked";
}) {
  "use step";
  // Best-effort like pulpo's _log_step -- logging failures must never abort the flow.
  try {
    await getDb().insert(flowRunSteps).values({
      runId: params.runId,
      nodeId: params.nodeId,
      nodeType: params.nodeType,
      inputState: params.inputState,
      outputState: params.outputState,
      status: params.status,
    });
  } catch (err) {
    console.error("[flow] failed to log step (non-fatal)", err);
  }
}

export async function runNodeStep(
  nodeType: string,
  nodeId: string,
  inDegree: number,
  config: Record<string, unknown>,
  state: FlowState
): Promise<{ state: FlowState; error: string | null }> {
  "use step";
  const nodeDef = NODE_REGISTRY[nodeType];
  if (!nodeDef) {
    // Unimplemented node type -- tolerant like the Python BFS: skip, don't abort.
    return { state, error: null };
  }
  // Matches pulpo/graphs/compiler.py's execute_flow(), which injects these
  // into every node's config before instantiating it (condition/router use
  // _node_id for their max_visits counters).
  const fullConfig = { ...config, _node_id: nodeId, _in_degree: inDegree };
  try {
    const nextState = await nodeDef.run(structuredClone(state), fullConfig);
    return { state: nextState, error: null };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { state, error: message };
  }
}
