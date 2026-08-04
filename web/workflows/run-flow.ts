import { getWorkflowMetadata } from "workflow";
import { startConversation } from "@/lib/flow/conversation";
import { expandNodeFlows } from "@/lib/flow/expand-node-flows";
import { buildGraph, enqueueNeighbors, inDegrees, type FlowEdgeDef, type FlowNodeDef } from "@/lib/flow/graph";
import {
  accumulateGate,
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
// try/except BFS. Deliberately out of scope: __start__/__end__ visual
// markers.
//
// gate (AND-join) blocks like wait_user -- this run ends without enqueuing
// gate's neighbors -- but does NOT persist resumeNodeId/slotsJson, because
// there's nothing to "resume": each distinct trigger/path that reaches the
// gate is its own independent run that walks the graph from its own entry
// point and re-arrives at the same gate node, accumulating into gate_waits
// (see lib/flow/steps.ts::accumulateGate) until enough paths have arrived.
// The run that completes the count continues past the gate in-place.
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

  let state = initialState;
  // Reanudar un wait_user ya llamó continueConversation() antes de esta
  // llamada (ver el webhook route) -- el guard de startConversation() lo
  // hace no-op ahí. Para un trigger "puro" (primer turno), esto arranca la
  // conversación de este run. Tiene que correr ANTES de startFlowRun (que
  // persiste `state` como trigger_data) -- si no, el snapshot guardado
  // queda sin `data.conversation` aunque la ejecución en memoria sí lo
  // tenga (mismo orden que el Python original, ver compiler.py).
  startConversation(state);

  await startFlowRun({
    runId,
    flowId,
    botId,
    connectionId,
    contactPhone: initialState.contactPhone || null,
    triggerData: initialState,
    workflowRunId,
  });

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
    // branchTaken solo si ESTE nodo cambió route -- no basta con que route
    // tenga un valor: un passthrough (subflow_end, subflow_start, gate,
    // wait_user) no rutea, solo hereda el route de un condition/router de
    // hops atrás y lo deja pasar para que enqueueNeighbors lo siga usando
    // más adelante (ver graph.ts). Reportar el ambiente en vez del cambio
    // real fue el bug original (branchTaken pegado en nodos downstream que
    // no rutean, cortaba el camino resaltado en el visor de runs) -- y
    // limpiar route apenas se usa una vez (intento previo de fix) rompía el
    // passthrough de subflow_end, que necesita ese route varios hops
    // después para rutear el flow padre (ver test de compiler.py:
    // test_route_sobrevive_a_subflow_end_para_rutear_el_padre).
    const routeBefore = (state.data.route as string) || null;

    if (nodeDef.type === "gate") {
      const waitFor = inDegree[currentId] ?? 2;
      const { opened, messages, previousWaitingRunId } = await accumulateGate({
        nodeId: currentId,
        contactPhone: state.contactPhone || "",
        message: state.message || "",
        waitFor,
        runId,
      });

      if (!opened) {
        hadWaitingGate = true;
        await logFlowStep({
          runId,
          nodeId: currentId,
          nodeType: "gate",
          inputState,
          outputState: state,
          status: "blocked",
        });
        // Igual que wait_user: no se encolan vecinos, este run termina acá.
        continue;
      }

      state = { ...state, data: { ...state.data, gate_messages: messages } };
      if (previousWaitingRunId && previousWaitingRunId !== runId) {
        await endFlowRun(previousWaitingRunId, "handed_off");
      }
      {
        const routeAfter = (state.data.route as string) || null;
        await logFlowStep({
          runId,
          nodeId: currentId,
          nodeType: "gate",
          inputState,
          outputState: state,
          branchTaken: routeAfter !== routeBefore ? routeAfter : null,
          status: "ok",
        });
      }
      enqueueNeighbors(graph, currentId, visited, queue, state);
      continue;
    }

    if (nodeDef.type === "wait_user") {
      const neighbors = graph[currentId] ?? [];
      const resumeNodeId = neighbors[0]?.target ?? null;
      if (resumeNodeId) {
        hadWaitingGate = true;
        await markWaitingGate({ runId, resumeNodeId, slotsJson: state.data });
      } else {
        console.warn(`[flow] wait_user en nodo ${currentId} sin nodo siguiente -- no hay dónde reanudar, se ignora la pausa`);
      }
      {
        const routeAfter = (state.data.route as string) || null;
        await logFlowStep({
          runId,
          nodeId: currentId,
          nodeType: "wait_user",
          inputState,
          outputState: state,
          branchTaken: routeAfter !== routeBefore ? routeAfter : null,
          status: "ok",
        });
      }
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

    const routeAfter = (state.data.route as string) || null;
    await logFlowStep({
      runId,
      nodeId: currentId,
      nodeType: nodeDef.type,
      inputState,
      outputState: error ? null : state,
      branchTaken: error || routeAfter === routeBefore ? null : routeAfter,
      status: error ? "error" : "ok",
      errorMessage: error ?? undefined,
    });

    enqueueNeighbors(graph, currentId, visited, queue, state);
  }

  await endFlowRun(runId, hadError ? "error" : hadWaitingGate ? "waiting_gate" : "completed");
  return { runId, state };
}
