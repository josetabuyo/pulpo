/**
 * Gemelo read-only del flow para la vista "Ver" de una corrida de test (tab
 * "Test" > "Ver"). A propósito NO es un dibujo aparte: monta el mismo
 * FlowCanvas.jsx del editor real, en modo `readOnly` (sin drag/editar, pero
 * CON zoom/pan/Controls -- a diferencia de `embed`, que usa la captura
 * headless en EmbedTestRunPage.jsx y apaga zoom/pan a propósito para que el
 * screenshot sea determinístico), con
 * `highlightNodeIds`/`highlightEdgeIds` para grisar todo menos el camino
 * que efectivamente se recorrió en esta corrida puntual (ver
 * utils/executionTrace.js). Mismos colores/posiciones/routing de edges que
 * el editor -- si el editor cambia de estilo, esto lo hereda gratis.
 *
 * Usa su propio store aislado (createFlowStore) cargado con el
 * `flow_snapshot` de la corrida -- NO el flow en vivo del bot, que puede
 * haber cambiado desde que se corrió el caso.
 */
import { useEffect, useMemo } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import { useFlowStore, createFlowStore, FlowStoreContext } from '../../store/flowStore.js'
import FlowCanvas from '../FlowCanvas.jsx'
import { buildExecutionTrace } from '../../utils/executionTrace.js'

function FlowExecutionTwinInner({ flowSnapshot, steps, apiCall }) {
  const loadFlow = useFlowStore(s => s.loadFlow)
  const setTypeMap = useFlowStore(s => s.setTypeMap)
  const nodes = useFlowStore(s => s.nodes)
  const edges = useFlowStore(s => s.edges)

  useEffect(() => {
    let cancelled = false
    apiCall('GET', '/flows/node-types', null)
      .then(typeList => {
        if (cancelled) return
        const typeMap = Object.fromEntries((Array.isArray(typeList) ? typeList : []).map(t => [t.id, t]))
        setTypeMap(typeMap)
        loadFlow(flowSnapshot, typeMap)
      })
      .catch(() => { if (!cancelled) loadFlow(flowSnapshot, {}) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowSnapshot])

  const { nodeIds: highlightNodeIds, edgeIds: highlightEdgeIds } = useMemo(
    () => buildExecutionTrace(steps, edges),
    [steps, edges],
  )

  return (
    <FlowCanvas
      readOnly
      nodes={nodes}
      edges={edges}
      onNodesChange={() => {}}
      onEdgesChange={() => {}}
      highlightNodeIds={highlightNodeIds}
      highlightEdgeIds={highlightEdgeIds}
    />
  )
}

export default function FlowExecutionTwin({ flowSnapshot, steps, apiCall, height = 640 }) {
  const store = useMemo(() => createFlowStore(), [])

  if (!flowSnapshot) {
    return <div className="empty" style={{ padding: '16px 0' }}>Sin snapshot del flow guardado para esta corrida</div>
  }

  return (
    <div style={{ height, flexShrink: 0, border: '1px solid var(--surface-2)', borderRadius: 8, overflow: 'hidden', position: 'relative', display: 'flex' }}>
      <FlowStoreContext.Provider value={store}>
        <ReactFlowProvider>
          <FlowExecutionTwinInner flowSnapshot={flowSnapshot} steps={steps} apiCall={apiCall} />
        </ReactFlowProvider>
      </FlowStoreContext.Provider>
    </div>
  )
}
