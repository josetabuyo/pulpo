import { getWorkflowMetadata } from "workflow";
import { buildGraph, enqueueNeighbors, type FlowEdgeDef, type FlowNodeDef } from "@/lib/flow/graph";
import { endFlowRun, loadFlow, logFlowStep, runNodeStep, startFlowRun } from "@/lib/flow/steps";
import type { FlowState } from "@/lib/nodes/state";

// TS port of execute_flow + _run_bfs (pulpo/graphs/compiler.py), using
// Workflow DevKit as the durable executor instead of a hand-rolled
// try/except BFS. Deliberately out of scope for this spike (ported later
// once the fit is validated): sub-flow expansion (expand_node_flows), gate
// and wait_user (pause/resume -- Workflow DevKit's createHook() is the
// natural replacement, see foundations/hooks.mdx), and __start__/__end__
// visual markers.
export async function runFlowWorkflow(
  flowId: string,
  entryNodeId: string,
  initialState: FlowState
): Promise<{ runId: string; state: FlowState }> {
  "use workflow";

  const { workflowRunId } = getWorkflowMetadata();
  const runId = workflowRunId;

  const { botId, connectionId, nodes, edges } = await loadFlow(flowId);
  await startFlowRun({
    runId,
    flowId,
    botId,
    connectionId,
    triggerData: initialState,
    workflowRunId,
  });

  const nodeById: Record<string, FlowNodeDef> = {};
  for (const node of nodes as FlowNodeDef[]) nodeById[node.id] = node;
  const graph = buildGraph(edges as FlowEdgeDef[]);

  const visited = new Set<string>();
  const queue: string[] = [entryNodeId];
  let state = initialState;
  let hadError = false;

  while (queue.length > 0) {
    const currentId = queue.shift() as string;
    if (visited.has(currentId)) continue;
    visited.add(currentId);

    const nodeDef = nodeById[currentId];
    if (!nodeDef) continue;

    const inputState = state;
    const { state: nextState, error } = await runNodeStep(nodeDef.type, nodeDef.config, state);
    state = nextState;
    if (error) hadError = true;

    await logFlowStep({
      runId,
      nodeId: currentId,
      nodeType: nodeDef.type,
      inputState,
      outputState: error ? null : state,
      status: error ? "error" : "ok",
    });

    const route = (state.data.route as string) || "";
    enqueueNeighbors(graph, currentId, visited, queue, route);
  }

  await endFlowRun(runId, hadError ? "error" : "completed");
  return { runId, state };
}
