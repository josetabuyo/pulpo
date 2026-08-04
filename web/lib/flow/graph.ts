// TS port of _build_graph / _enqueue_neighbors (pulpo/graphs/compiler.py).
// Pure logic, no I/O -- safe to call directly from a "use workflow" function.
import type { FlowState } from "@/lib/nodes/state";

export interface FlowNodeDef {
  id: string;
  type: string;
  config: Record<string, unknown>;
}

export interface FlowEdgeDef {
  source: string;
  target: string;
  label?: string | null;
}

export type Graph = Record<string, Array<{ target: string; label: string | null }>>;

export function buildGraph(edges: FlowEdgeDef[]): Graph {
  const graph: Graph = {};
  for (const edge of edges) {
    if (!edge.source || !edge.target) continue;
    graph[edge.source] ??= [];
    graph[edge.source].push({ target: edge.target, label: edge.label || null });
  }
  return graph;
}

export function inDegrees(graph: Graph): Record<string, number> {
  const degrees: Record<string, number> = {};
  for (const targets of Object.values(graph)) {
    for (const { target } of targets) {
      degrees[target] = (degrees[target] ?? 0) + 1;
    }
  }
  return degrees;
}

// Puramente de lectura -- NO limpia route de state.data. Un subflowEnd
// (passthrough puro, no vuelve a setear route) depende de que el route que
// dejó un condition/router de varios hops atrás siga vivo acá para poder
// salir por el edge externo correcto del nodo_flow que lo contiene (ver
// expand-node-flows.ts). Limpiarlo acá rompe ese passthrough -- bug real
// encontrado al arreglar el leak de branchTaken (ver run-flow.ts, donde se
// resuelve comparando route antes/después de CADA nodo en vez de tocar esto).
export function enqueueNeighbors(
  graph: Graph,
  nodeId: string,
  visited: Set<string>,
  queue: string[],
  state: FlowState
) {
  const currentRoute = (state.data.route as string) || "";
  for (const { target, label } of graph[nodeId] ?? []) {
    if (visited.has(target)) continue;
    if (label === null || label === "" || currentRoute === label) {
      queue.push(target);
    }
  }
}
