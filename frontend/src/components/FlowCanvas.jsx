import { useEffect, useState, useCallback } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'

// ─── Colores por tipo de nodo ───────────────────────────────────────────────

const NODE_STYLES = {
  start:    { background: '#166534', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  end:      { background: '#991b1b', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  router:   { background: '#854d0e', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  fetch:    { background: '#1e40af', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  llm:      { background: '#6b21a8', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  reply:    { background: '#374151', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  notify:   { background: '#9a3412', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  summarize:{ background: '#14532d', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
  generic:  { background: '#1e293b', color: '#fff', borderRadius: 8, border: 'none', padding: '8px 16px', fontSize: 13 },
}

// ─── Layout con dagre ────────────────────────────────────────────────────────

const NODE_WIDTH = 140
const NODE_HEIGHT = 40

function applyDagreLayout(rawNodes, rawEdges) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', ranksep: 60, nodesep: 40 })

  for (const n of rawNodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const e of rawEdges) {
    g.setEdge(e.source, e.target)
  }

  dagre.layout(g)

  const nodes = rawNodes.map(n => {
    const pos = g.node(n.id)
    return {
      id: n.id,
      data: { label: n.label },
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      style: NODE_STYLES[n.type] || NODE_STYLES.generic,
    }
  })

  const edges = rawEdges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
    style: { stroke: '#64748b' },
    labelStyle: { fill: '#94a3b8', fontSize: 11 },
  }))

  return { nodes, edges }
}

// ─── FlowCanvas ──────────────────────────────────────────────────────────────

export default function FlowCanvas({ empresaId, apiCall }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => {
    setLoading(true)
    setError(null)
    apiCall('GET', `/empresas/${empresaId}/flow/graph`)
      .then(graph => {
        if (!graph || !graph.nodes) {
          setError('Respuesta inválida del servidor')
          return
        }
        const { nodes: n, edges: e } = applyDagreLayout(graph.nodes, graph.edges)
        setNodes(n)
        setEdges(e)
      })
      .catch(err => setError('Error al cargar el grafo'))
      .finally(() => setLoading(false))
  }, [empresaId])

  if (loading) {
    return <div className="empty" style={{ padding: '32px 20px' }}>Cargando flow...</div>
  }

  if (error) {
    return <div className="empty" style={{ padding: '32px 20px', color: '#ef4444' }}>{error}</div>
  }

  return (
    <div style={{ height: 360, background: '#0f172a', borderRadius: 8, overflow: 'hidden' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={true}
        zoomOnScroll={true}
      >
        <Background color="#1e293b" gap={16} />
        <Controls showInteractive={false} style={{ background: '#1e293b', border: '1px solid #334155' }} />
      </ReactFlow>
    </div>
  )
}
