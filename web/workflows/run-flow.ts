import { getWorkflowMetadata } from "workflow";
import { startConversation } from "@/lib/flow/conversation";
import { expandNodeFlows } from "@/lib/flow/expand-node-flows";
import { buildGraph, enqueueNeighbors, inDegrees, type FlowEdgeDef, type FlowNodeDef } from "@/lib/flow/graph";
import {
  endFlowRun,
  fetchFlowDefinition,
  loadFlow,
  logFlowStep,
  markWaitingGate,
  runNodeStep,
  startFlowRun,
} from "@/lib/flow/steps";
import type { FlowState } from "@/lib/nodes/state";

// TS port of execute_flow + _run_bfs (pulpo/graphs/compiler.py), using
// Workflow DevKit as the durable executor instead of a hand-rolled
// try/except BFS. Deliberately out of scope: gate (AND-join, only wait_user
// is ported), __start__/__end__ visual markers.
//
// wait_user pauses this run entirely rather than suspending mid-workflow with
// createHook() -- deliberate architecture choice (2026-07-22, see handoff
// doc) mirroring the Python original exactly: each conversation turn is a
// SEPARATE flow run. When BFS reaches wait_user, this run ends with status
// "waiting_gate" (resumeNodeId + the current state persisted as slotsJson,
// flow_runs columns that already existed in the schema for this). The next
// Telegram message for that (bot, contact) resumes by starting a NEW
// runFlowWorkflow call with entryNodeId = resumeNodeId and the restored
// state -- see app/api/telegram/webhook/[tokenId]/route.ts. This avoids
// relying on a single long-lived suspended workflow run per open
// conversation, and reuses flow_runs.status/resumeNodeId/slotsJson exactly
// like the Python side's DB-backed wait_user_info.
export async function runFlowWorkflow(
  flowId: string,
  entryNodeId: string,
  initialState: FlowState
): Promise<{ runId: string; state: FlowState }> {
  "use workflow";

  const { workflowRunId } = getWorkflowMetadata();
  const runId = workflowRunId;

  const { botId, connectionId, nodes: rawNodes, edges: rawEdges } = await loadFlow(flowId);

  let nodes = rawNodes as FlowNodeDef[];
  let edges = rawEdges as FlowEdgeDef[];
  if (nodes.some((n) => n.type === "nodo_flow")) {
    const expanded = await expandNodeFlows(nodes, edges, fetchFlowDefinition);
    nodes = expanded.nodes;
    edges = expanded.edges;
  }

  await startFlowRun({
    runId,
    flowId,
    botId,
    connectionId,
    contactPhone: initialState.contactPhone || null,
    triggerData: initialState,
    workflowRunId,
  });

  let state = initialState;
  // Reanudar un wait_user ya llamó continueConversation() antes de esta
  // llamada (ver el webhook route) -- el guard de startConversation() lo
  // hace no-op ahí. Para un trigger "puro" (primer turno), esto arranca la
  // conversación de este run.
  startConversation(state);

  const nodeById: Record<string, FlowNodeDef> = {};
  for (const node of nodes) nodeById[node.id] = node;
  const graph = buildGraph(edges);
  const inDegree = inDegrees(graph);

  const visited = new Set<string>();
  const queue: string[] = [entryNodeId];
  let hadError = false;
  let hadWaitingGate = false;

  while (queue.length > 0) {
    const currentId = queue.shift() as string;
    if (visited.has(currentId)) continue;
    visited.add(currentId);

    const nodeDef = nodeById[currentId];
    if (!nodeDef) continue;

    const inputState = state;

    if (nodeDef.type === "wait_user") {
      const neighbors = graph[currentId] ?? [];
      const resumeNodeId = neighbors[0]?.target ?? null;
      if (resumeNodeId) {
        hadWaitingGate = true;
        await markWaitingGate({ runId, resumeNodeId, slotsJson: state.data });
      } else {
        console.warn(`[flow] wait_user en nodo ${currentId} sin nodo siguiente -- no hay dónde reanudar, se ignora la pausa`);
      }
      await logFlowStep({
        runId,
        nodeId: currentId,
        nodeType: "wait_user",
        inputState,
        outputState: state,
        status: "ok",
      });
      // Deliberadamente NO se llama enqueueNeighbors -- este run termina acá,
      // igual que gate_blocked en el compiler.py original.
      continue;
    }

    const { state: nextState, error } = await runNodeStep(
      nodeDef.type,
      currentId,
      inDegree[currentId] ?? 1,
      nodeDef.config,
      state
    );
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

  await endFlowRun(runId, hadError ? "error" : hadWaitingGate ? "waiting_gate" : "completed");
  return { runId, state };
}
