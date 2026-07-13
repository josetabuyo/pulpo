/**
 * EmbedFlowPage — solo-diagrama, para captura headless del reporte e2e.
 *
 * Monta el mismo FlowCanvas que el editor real (embed=true: sin Controls, sin
 * panel de config, sin interacción), full-bleed. No hay dibujo propio acá —
 * los colores/formas/edges siguen viniendo enteros de FlowCanvas.jsx.
 *
 * Ruta: /embed/flow/:botId?flow=<flow_id>
 *   - Con ?flow=<id>: captura ese flow puntual.
 *   - Sin ?flow=: captura el (único) flow activo del bot.
 *
 * La API de flows no requiere auth (ver pulpo/interfaces/api/routers/flows.py),
 * así que esta página no hace login — solo lee.
 *
 * Señaliza al script de captura headless (tests/e2e/luganense/capture_diagram.py)
 * vía window.__flowReady / window.__flowError, seteados recién después de que
 * el flow cargó Y React Flow hizo fitView (evento onInit + doble rAF).
 */
import { useEffect, useState, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { ReactFlowProvider } from '@xyflow/react'

import { useFlowStore, createFlowStore, FlowStoreContext } from '../store/flowStore.js'
import FlowCanvas from '../components/FlowCanvas.jsx'

function markReady() {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    window.__flowReady = true
  }))
}

function EmbedFlowInner({ botId, flowIdParam }) {
  const loadFlow   = useFlowStore(s => s.loadFlow)
  const setTypeMap = useFlowStore(s => s.setTypeMap)
  const nodes      = useFlowStore(s => s.nodes)
  const edges      = useFlowStore(s => s.edges)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    async function run() {
      try {
        const [typesRes, flowsRes] = await Promise.all([
          fetch('/api/flows/node-types', { signal: controller.signal }),
          fetch(`/api/flows/bots/${botId}`, { signal: controller.signal }),
        ])
        if (!typesRes.ok) throw new Error(`GET /flows/node-types → ${typesRes.status}`)
        if (!flowsRes.ok) throw new Error(`GET /flows/bots/${botId} → ${flowsRes.status}`)

        const typeList = await typesRes.json()
        const typeMap = Object.fromEntries((typeList || []).map(t => [t.id, t]))
        const flows = await flowsRes.json()

        const flowSummary = flowIdParam
          ? flows.find(f => f.id === flowIdParam)
          : flows.find(f => f.active)
        if (!flowSummary) {
          throw new Error(
            flowIdParam
              ? `No se encontró el flow id=${flowIdParam} para bot=${botId}`
              : `bot=${botId} no tiene ningún flow activo`
          )
        }

        const fullRes = await fetch(`/api/flows/bots/${botId}/${flowSummary.id}`, { signal: controller.signal })
        if (!fullRes.ok) throw new Error(`GET /flows/bots/${botId}/${flowSummary.id} → ${fullRes.status}`)
        const full = await fullRes.json()

        if (cancelled) return
        setTypeMap(typeMap)
        loadFlow(full.definition, typeMap)
      } catch (e) {
        if (cancelled || e.name === 'AbortError') return
        setError(e.message)
        window.__flowError = e.message
      }
    }
    run()
    return () => { cancelled = true; controller.abort() }
  }, [botId, flowIdParam, loadFlow, setTypeMap])

  // Recién marcamos "listo" cuando ya hay nodos cargados — el fitView real
  // se confirma con el onInit que le pasamos a FlowCanvas más abajo.
  const hasContent = nodes.length > 0

  if (error) {
    return (
      <div style={{ padding: 24, color: '#f87171', fontFamily: 'monospace', fontSize: 13 }}>
        Error cargando el flow: {error}
      </div>
    )
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#0f172a', display: 'flex' }}>
      <FlowCanvas
        embed
        nodes={nodes}
        edges={edges}
        onNodesChange={() => {}}
        onEdgesChange={() => {}}
        onInit={hasContent ? markReady : undefined}
      />
    </div>
  )
}

export default function EmbedFlowPage() {
  const { botId } = useParams()
  const [searchParams] = useSearchParams()
  const flowIdParam = searchParams.get('flow')
  const store = useMemo(() => createFlowStore(), [])

  return (
    <FlowStoreContext.Provider value={store}>
      <ReactFlowProvider>
        <EmbedFlowInner botId={botId} flowIdParam={flowIdParam} />
      </ReactFlowProvider>
    </FlowStoreContext.Provider>
  )
}
