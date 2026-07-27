/**
 * Reconstruye qué nodos/edges de un flow se recorrieron efectivamente en una
 * corrida puntual, a partir de la secuencia de steps (StepDto, ver
 * web/lib/business/test-checks.ts: node_id/branch_taken concatenados de
 * todos los turnos). Usado por FlowExecutionTwin.jsx (tab "Test" > "Ver") y
 * por FlowCanvas.jsx vía `highlightNodeIds`/`highlightEdgeIds` -- mismo
 * mecanismo de resaltado que usa el editor real, no un dibujo aparte.
 *
 * Traza una edge por adyacencia consecutiva en la secuencia de steps -- y si
 * el nodo origen es un router/condition (`branch_taken` seteado), solo
 * cuenta como recorrida la edge cuyo label coincide con la rama tomada.
 */
// Los steps de un nodo `nodo_flow` (sub-flow embebido) se loguean con id
// compuesto "padre::interno" (uno por paso DENTRO del sub-flow, ver
// pulpo/graphs/compiler.py) -- ninguno de esos ids compuestos existe en
// `flow_snapshot.nodes`/`edges` de ESTE flow, solo el id del nodo_flow en
// sí. `topLevel()` pela el prefijo para poder matchear contra el snapshot.
function topLevel(nodeId) {
  const i = nodeId.indexOf('::')
  return i === -1 ? nodeId : nodeId.slice(0, i)
}

export function buildExecutionTrace(steps, edges) {
  const list = steps || []
  const nodeIds = new Set(list.map(s => topLevel(s.node_id)))

  // Colapsar corridas consecutivas del mismo nodo top-level (todos los
  // steps internos de un mismo nodo_flow) a una sola entrada -- así la
  // adyacencia se traza entre nodos TOP-LEVEL, que es lo único que
  // `edges` conoce. Si algún step interno seteó branch_taken, se propaga
  // a la entrada colapsada.
  const collapsed = []
  for (const s of list) {
    const id = topLevel(s.node_id)
    const last = collapsed[collapsed.length - 1]
    if (last && last.id === id) {
      if (s.branch_taken) last.branch_taken = s.branch_taken
      continue
    }
    collapsed.push({ id, branch_taken: s.branch_taken || null })
  }

  // Clave compuesta con la rama tomada (o '' si el nodo no es router/no la
  // seteó) -- necesario para no perder información cuando el MISMO router
  // se visita más de una vez en la corrida (turnos distintos) con ramas
  // distintas, algo real en esta suite (ver "Confirmó la propuesta?" en los
  // casos de comercio: rechaza en un turno, confirma en el siguiente).
  const tracedKeys = new Set()
  for (let i = 0; i < collapsed.length - 1; i++) {
    tracedKeys.add(`${collapsed[i].id}->${collapsed[i + 1].id}::${collapsed[i].branch_taken || ''}`)
  }

  const edgeIds = new Set()
  for (const e of edges || []) {
    if (tracedKeys.has(`${e.source}->${e.target}::${e.label || ''}`)) edgeIds.add(e.id)
  }

  return { nodeIds, edgeIds }
}
