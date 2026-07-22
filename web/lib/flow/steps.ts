import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { flowRunSteps, flowRuns, flows } from "@/lib/db/schema";
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
  triggerData: unknown;
  workflowRunId: string;
}) {
  "use step";
  await getDb().insert(flowRuns).values({
    runId: params.runId,
    flowId: params.flowId,
    botId: params.botId,
    connectionId: params.connectionId,
    status: "running",
    triggerData: params.triggerData,
    workflowRunId: params.workflowRunId,
  });
}

export async function endFlowRun(runId: string, status: string) {
  "use step";
  await getDb().update(flowRuns).set({ status, endedAt: new Date() }).where(eq(flowRuns.runId, runId));
}

export async function logFlowStep(params: {
  runId: string;
  nodeId: string;
  nodeType: string;
  inputState: unknown;
  outputState: unknown;
  status: "ok" | "error";
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
  config: Record<string, unknown>,
  state: FlowState
): Promise<{ state: FlowState; error: string | null }> {
  "use step";
  const nodeDef = NODE_REGISTRY[nodeType];
  if (!nodeDef) {
    // Unimplemented node type -- tolerant like the Python BFS: skip, don't abort.
    return { state, error: null };
  }
  try {
    const nextState = await nodeDef.run(structuredClone(state), config);
    return { state: nextState, error: null };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { state, error: message };
  }
}
