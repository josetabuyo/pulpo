/**
 * Reconstruye qué nodos/edges de un flow se recorrieron efectivamente en una
 * corrida puntual, a partir de la secuencia de steps (StepDto, ver
 * web/lib/business/test-checks.ts: node_id/branch_taken concatenados de
 * todos los turnos). Usado por FlowExecutionTwin.jsx (tab "Test" > "Ver") y
 * por FlowCanvas.jsx vía `highlightNodeIds`/`highlightEdgeIds` -- mismo
 * mecanismo de resaltado que usa el editor real, no un dibujo aparte.
 *
 * Traza una edge por adyacencia consecutiva en la secuencia de steps -- y si
 * el nodo origen es un router/condition (`branch_taken` seteado) O un
 * nodo_flow que salió por una ruta con nombre (ver `subflowRoute()` abajo),
 * solo cuenta como recorrida la edge cuyo label coincide con la rama tomada.
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

// Fallback para un nodo_flow con salidas nombradas cuyo subflow_end se
// alcanza SIN que ningún step propio del sub-flow haya logueado
// branch_taken (ej. ramificación puramente estructural, sin un
// condition/router explícito de por medio) -- en ese caso la ruta de salida
// queda codificada en el id del subflow_end ("padre::sf_end_<ruta>", ver
// pulpo/graphs/compiler.py). SOLO se usa como último recurso: el id es un
// nombre elegido a mano en el editor y puede no coincidir textualmente con
// el label real del edge (ej. id "sf_end_notfound" para el label
// "not_found", bug real 2026-08-04) -- el branch_taken real que haya
// logueado un step anterior del mismo nodo_flow (ver buildExecutionTrace)
// SIEMPRE tiene prioridad sobre esta adivinanza.
function subflowRoute(nodeId) {
  const m = nodeId.match(/::sf_end_(.+)$/)
  return m ? m[1] : null
}

export function buildExecutionTrace(steps, edges) {
  const list = steps || []
  const nodeIds = new Set(list.map(s => topLevel(s.node_id)))

  // Colapsar corridas consecutivas del mismo nodo top-level (todos los
  // steps internos de un mismo nodo_flow) a una sola entrada -- así la
  // adyacencia se traza entre nodos TOP-LEVEL, que es lo único que
  // `edges` conoce. El branch_taken real (columna de DB) de cualquier step
  // interno siempre pisa un guess de subflowRoute() -- el guess solo llena
  // el hueco si el grupo todavía no tiene ningún branch_taken real.
  const collapsed = []
  for (const s of list) {
    const id = topLevel(s.node_id)
    const last = collapsed[collapsed.length - 1]
    if (last && last.id === id) {
      if (s.branch_taken) {
        last.branch_taken = s.branch_taken
      } else if (!last.branch_taken) {
        const guessed = subflowRoute(s.node_id)
        if (guessed) last.branch_taken = guessed
      }
      continue
    }
    collapsed.push({ id, branch_taken: s.branch_taken || subflowRoute(s.node_id) || null })
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
