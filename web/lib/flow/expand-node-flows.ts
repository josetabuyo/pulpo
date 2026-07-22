import type { FlowEdgeDef, FlowNodeDef } from "./graph";

// TS port of expand_node_flows (pulpo/graphs/compiler.py) -- expands every
// `nodo_flow` node inline, replacing it with the referenced sub-flow's nodes/
// edges (see management/SPEC_NODOFLOW.md in the Python side, and the ADR
// referenced there: "subgraph expansion, not sub-execution"). Pure function
// over (nodes, edges) -- loads sub-flows via the injected `fetchFlow`
// callback (a "use step" in production, a plain async fn in tests), same
// separation as the Python original.
//
// Mechanics per nodo_flow node:
//   - Namespaces the subgraph with a `${nodoFlowId}::` prefix.
//   - Recursively expands (nested NodoFlow), passing `visiting ∪ {flowId}` so
//     the recursion never re-enters the same flow (cycle detection).
//   - Inserts synthetic `set_state` nodes to inject parameters (any config
//     key on the nodo_flow node other than flow_id/output/routes) before the
//     sub-flow's root. `output`, if set, is forwarded as a parameter too --
//     the sub-flow can read {{output}} to know which state key to write its
//     result to.
//   - Reconnects the external edges that pointed in/out of the nodo_flow node.
//
// A sub-flow declares exactly one `subflow_start` (its root) and one or more
// `subflow_end` (its exits, each labeled by `config.route`) -- both are real
// passthrough nodes that DO execute (lib/nodes/subflow.ts).

export type FetchFlowFn = (flowId: string) => Promise<{ nodes?: FlowNodeDef[]; edges?: FlowEdgeDef[] } | null>;

const RESERVED_PARAM_KEYS = new Set(["flow_id", "output", "routes"]);

export async function expandNodeFlows(
  nodes: FlowNodeDef[],
  edges: FlowEdgeDef[],
  fetchFlow: FetchFlowFn,
  visiting: Set<string> = new Set(),
): Promise<{ nodes: FlowNodeDef[]; edges: FlowEdgeDef[] }> {
  const toExpand = nodes.filter((n) => n.type === "nodo_flow" && Boolean((n.config as Record<string, unknown> | undefined)?.flow_id));
  if (toExpand.length === 0) return { nodes, edges };

  const expandedIdSet = new Set(toExpand.map((n) => n.id));
  const outNodes: FlowNodeDef[] = nodes.filter((n) => !expandedIdSet.has(n.id));

  const addedNodes: FlowNodeDef[] = [];
  const addedEdges: FlowEdgeDef[] = [];
  const entryOf: Record<string, string> = {};
  const exitsOf: Record<string, string[]> = {};

  for (const node of toExpand) {
    const nfid = node.id;
    const cfg = (node.config ?? {}) as Record<string, unknown>;
    const flowId = String(cfg.flow_id);

    if (visiting.has(flowId)) {
      throw new Error(`Ciclo de NodoFlow detectado: ${flowId} se referencia a sí mismo o forma un ciclo`);
    }

    const definition = await fetchFlow(flowId);
    if (!definition) throw new Error(`NodoFlow referencia un flow inexistente: ${flowId}`);

    const innerNodes = definition.nodes ?? [];
    const innerEdges = definition.edges ?? [];
    const prefix = `${nfid}::`;

    const nsNodes: FlowNodeDef[] = innerNodes.map((n) => ({ ...n, id: prefix + n.id }));
    const nsEdges: FlowEdgeDef[] = innerEdges.map((e) => ({ ...e, source: prefix + e.source, target: prefix + e.target }));

    const starts = nsNodes.filter((n) => n.type === "subflow_start").map((n) => n.id);
    if (starts.length === 0) {
      throw new Error(`El NodoFlow '${flowId}' necesita exactamente un nodo de Inicio (subflow_start)`);
    }
    if (starts.length > 1) {
      throw new Error(`El NodoFlow '${flowId}' tiene más de un nodo de Inicio (subflow_start); no soportado en v1`);
    }
    const root = starts[0];

    const endNodes = nsNodes.filter((n) => n.type === "subflow_end");
    if (endNodes.length === 0) {
      throw new Error(`El NodoFlow '${flowId}' necesita al menos un nodo de Fin (subflow_end)`);
    }
    const exitConns: string[] = endNodes.map((n) => n.id);

    const expanded = await expandNodeFlows(nsNodes, nsEdges, fetchFlow, new Set([...visiting, flowId]));
    const subAddedNodes = [...expanded.nodes];
    const subAddedEdges = [...expanded.edges];

    const params: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(cfg)) {
      if (!RESERVED_PARAM_KEYS.has(key)) params[key] = value;
    }
    if (cfg.output) params.output = cfg.output;

    const paramNodeIds: string[] = [];
    let i = 0;
    for (const [key, value] of Object.entries(params)) {
      const pid = `${nfid}::__params__${i}`;
      paramNodeIds.push(pid);
      subAddedNodes.push({ id: pid, type: "set_state", config: { field: key, value: String(value) } });
      i++;
    }
    for (let j = 0; j < paramNodeIds.length - 1; j++) {
      subAddedEdges.push({ source: paramNodeIds[j], target: paramNodeIds[j + 1], label: null });
    }
    let entryTarget: string;
    if (paramNodeIds.length > 0) {
      subAddedEdges.push({ source: paramNodeIds[paramNodeIds.length - 1], target: root, label: null });
      entryTarget = paramNodeIds[0];
    } else {
      entryTarget = root;
    }

    entryOf[nfid] = entryTarget;
    exitsOf[nfid] = Array.from(new Set(exitConns));
    addedNodes.push(...subAddedNodes);
    addedEdges.push(...subAddedEdges);
  }

  const outEdges: FlowEdgeDef[] = [];
  for (const e of edges) {
    const newSources = e.source in exitsOf ? exitsOf[e.source] : [e.source];
    const newTargets = e.target in entryOf ? [entryOf[e.target]] : [e.target];
    for (const s of newSources) {
      for (const t of newTargets) {
        outEdges.push({ ...e, source: s, target: t });
      }
    }
  }

  return { nodes: [...outNodes, ...addedNodes], edges: [...outEdges, ...addedEdges] };
}
