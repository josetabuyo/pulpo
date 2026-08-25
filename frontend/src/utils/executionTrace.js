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

// Normaliza para comparar un branch_taken/label contra el otro sin que
// mayúsculas, espacios o separadores (_/-) hagan fallar un match que en
// esencia es el mismo nombre de rama (ej. "sf_end_notfound" vs "not_found").
function norm(s) {
  return String(s ?? '').toLowerCase().replace(/[^a-z0-9]/g, '')
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
  // branchSource distingue el origen: un guess de subflowRoute() es un id
  // elegido a mano en el editor, coincidencia contra el label real no
  // garantizada -- por eso el matching de edges lo trata distinto (salta
  // directo a comparación normalizada en vez de exigir match exacto).
  const collapsed = []
  for (const s of list) {
    const id = topLevel(s.node_id)
    const last = collapsed[collapsed.length - 1]
    if (last && last.id === id) {
      if (s.branch_taken) {
        last.branch_taken = s.branch_taken
        last.branchSource = 'logged'
      } else if (!last.branch_taken) {
        const guessed = subflowRoute(s.node_id)
        if (guessed) { last.branch_taken = guessed; last.branchSource = 'guessed' }
      }
      continue
    }
    const branch_taken = s.branch_taken || subflowRoute(s.node_id) || null
    collapsed.push({
      id,
      branch_taken,
      branchSource: s.branch_taken ? 'logged' : (branch_taken ? 'guessed' : null),
    })
  }

  const edgesBySourceTarget = new Map()
  for (const e of edges || []) {
    const key = `${e.source}->${e.target}`
    if (!edgesBySourceTarget.has(key)) edgesBySourceTarget.set(key, [])
    edgesBySourceTarget.get(key).push(e)
  }

  // Para cada transición consecutiva a->b realmente recorrida (ambos nodos
  // están en nodeIds con certeza), resuelve CUÁL de las posibles edges
  // a->b fue la tomada -- en cascada, de la señal más confiable a la menos:
  //   1 sola edge entre a y b => es esa, no hace falta mirar el label.
  //   varias edges => match exacto de label (solo si branch fue LOGUEADO),
  //     luego match normalizado, luego match por contención si es único.
  //   ninguna de las anteriores desambiguó => marcar TODAS: la transición
  //     ocurrió con certeza, preferible resaltar una edge de más a cortar
  //     la rama visualmente en el nodo final (bug reportado 2026-08-25).
  const edgeIds = new Set()
  for (let i = 0; i < collapsed.length - 1; i++) {
    const a = collapsed[i]
    const b = collapsed[i + 1]
    const candidates = edgesBySourceTarget.get(`${a.id}->${b.id}`) || []
    if (candidates.length === 0) continue
    if (candidates.length === 1) {
      edgeIds.add(candidates[0].id)
      continue
    }

    const branch = a.branch_taken
    let matched = null

    if (branch && a.branchSource === 'logged') {
      matched = candidates.filter(e => (e.label || '') === branch)
      if (matched.length !== 1) matched = null
    }
    if (!matched && branch) {
      const normBranch = norm(branch)
      matched = candidates.filter(e => norm(e.label) === normBranch)
      if (matched.length !== 1) matched = null
    }
    if (!matched && branch) {
      const normBranch = norm(branch)
      matched = candidates.filter(e => {
        const normLabel = norm(e.label)
        return normLabel && (normLabel.includes(normBranch) || normBranch.includes(normLabel))
      })
      if (matched.length !== 1) matched = null
    }

    if (matched) {
      edgeIds.add(matched[0].id)
    } else {
      candidates.forEach(e => edgeIds.add(e.id))
    }
  }

  return { nodeIds, edgeIds }
}
