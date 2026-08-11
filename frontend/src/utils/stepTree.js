/**
 * Reconstruye la jerarquía nodo/sub-nodo de una corrida a partir del array
 * plano de `flow_run_steps`. El compiler namespacea el `node_id` de los
 * steps que corren dentro de un `nodo_flow` como "padre::interno"
 * (potencialmente anidado varias veces, ver lib/flow/expand-node-flows.ts::
 * expandNodeFlows y utils/executionTrace.js::topLevel -- mismo esquema).
 *
 * No hay columna de jerarquía en la DB (flow_run_steps es plana) ni un id
 * "padre" garantizado para cada nivel intermedio (un nodo_flow puede no
 * loguear step propio en su id exacto si el compiler saltó directo a su
 * subflow_start) -- por eso la reconstrucción es por PREFIJO de string, no
 * por profundidad contada de "::". Se arma con una pila de ancestros
 * abiertos: cada step nuevo se anida bajo el ancestro más profundo cuyo id
 * sea prefijo estricto del suyo, sin límite de anidamiento.
 */
export function buildStepTree(steps) {
  const roots = []
  const chain = [] // [{ id, node }] del más superficial al más profundo, todavía "abierto"

  for (const step of steps || []) {
    const nid = step.node_id
    while (chain.length && !nid.startsWith(`${chain[chain.length - 1].id}::`)) {
      chain.pop()
    }
    const parent = chain.length ? chain[chain.length - 1] : null
    const node = { step, id: nid, depth: chain.length, children: [] }
    if (parent) parent.node.children.push(node)
    else roots.push(node)
    chain.push({ id: nid, node })
  }

  return roots
}

// Profundidad máxima real del árbol (0 si es plano) -- para acotar el
// control de filtro de nivel a lo que la corrida realmente tiene.
export function maxTreeDepth(tree) {
  let max = 0
  const walk = (nodes) => {
    for (const n of nodes) {
      if (n.depth > max) max = n.depth
      if (n.children.length) walk(n.children)
    }
  }
  walk(tree)
  return max
}
