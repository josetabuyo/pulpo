/**
 * EmbedTestRunPage — mismo patrón que EmbedFlowPage.jsx (solo-diagrama, sin
 * login, para captura headless), pero para UNA corrida de test puntual: el
 * flow queda grisado salvo el camino que efectivamente se recorrió (mismo
 * mecanismo de highlight que FlowExecutionTwin.jsx, la vista "Ver" del
 * dashboard -- ver utils/executionTrace.js). Esta es la imagen que
 * lib/business/flow-capture.ts (web/) captura server-side después de CADA
 * corrida (UI o CLI, da igual quién la disparó) para que quede como parte
 * del reporte de test (test_runs.diagram_image).
 *
 * Ruta: /embed/test-run/:botId/:runId
 *
 * Señaliza igual que EmbedFlowPage vía window.__flowReady / __flowError.
 */
import { useEffect, useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { ReactFlowProvider } from '@xyflow/react'

import { useFlowStore, createFlowStore, FlowStoreContext } from '../store/flowStore.js'
import FlowCanvas from '../components/FlowCanvas.jsx'
import { buildExecutionTrace } from '../utils/executionTrace.js'

function markReady() {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    window.__flowReady = true
  }))
}

function EmbedTestRunInner({ botId, runId }) {
  const loadFlow   = useFlowStore(s => s.loadFlow)
  const setTypeMap = useFlowStore(s => s.setTypeMap)
  const nodes = useFlowStore(s => s.nodes)
  const edges = useFlowStore(s => s.edges)
  const [steps, setSteps] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    async function run() {
      try {
        const [typesRes, runRes] = await Promise.all([
          fetch('/api/flows/node-types', { signal: controller.signal }),
          fetch(`/api/bots/${botId}/test-runs/${runId}`, { signal: controller.signal }),
        ])
        if (!typesRes.ok) throw new Error(`GET /flows/node-types → ${typesRes.status}`)
        if (!runRes.ok) throw new Error(`GET /bots/${botId}/test-runs/${runId} → ${runRes.status}`)

        const typeList = await typesRes.json()
        const typeMap = Object.fromEntries((typeList || []).map(t => [t.id, t]))
        const run = await runRes.json()
        if (!run.flow_snapshot) throw new Error(`test_run ${runId} no tiene flow_snapshot guardado`)

        if (cancelled) return
        setTypeMap(typeMap)
        loadFlow(run.flow_snapshot, typeMap)
        setSteps(run.steps || [])
      } catch (e) {
        if (cancelled || e.name === 'AbortError') return
        setError(e.message)
        window.__flowError = e.message
      }
    }
    run()
    return () => { cancelled = true; controller.abort() }
  }, [botId, runId, loadFlow, setTypeMap])

  const { nodeIds: highlightNodeIds, edgeIds: highlightEdgeIds } = useMemo(
    () => buildExecutionTrace(steps || [], edges),
    [steps, edges],
  )

  const hasContent = nodes.length > 0 && steps !== null

  if (error) {
    return (
      <div style={{ padding: 24, color: 'var(--danger)', fontFamily: 'monospace', fontSize: 13 }}>
        Error cargando la corrida: {error}
      </div>
    )
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'var(--bg)', display: 'flex' }}>
      <FlowCanvas
        embed
        nodes={nodes}
        edges={edges}
        onNodesChange={() => {}}
        onEdgesChange={() => {}}
        highlightNodeIds={highlightNodeIds}
        highlightEdgeIds={highlightEdgeIds}
        onInit={hasContent ? markReady : undefined}
      />
    </div>
  )
}

export default function EmbedTestRunPage() {
  const { botId, runId } = useParams()
  const store = useMemo(() => createFlowStore(), [])

  return (
    <FlowStoreContext.Provider value={store}>
      <ReactFlowProvider>
        <EmbedTestRunInner botId={botId} runId={runId} />
      </ReactFlowProvider>
    </FlowStoreContext.Provider>
  )
}
