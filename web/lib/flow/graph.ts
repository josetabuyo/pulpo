// TS port of _build_graph / _enqueue_neighbors (pulpo/graphs/compiler.py).
// Pure logic, no I/O -- safe to call directly from a "use workflow" function.
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

export function enqueueNeighbors(
  graph: Graph,
  nodeId: string,
  visited: Set<string>,
  queue: string[],
  currentRoute: string
) {
  for (const { target, label } of graph[nodeId] ?? []) {
    if (visited.has(target)) continue;
    if (label === null || label === "" || currentRoute === label) {
      queue.push(target);
    }
  }
}
