import { useEffect, useState, useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'

// ─── Nodo custom con tooltip ─────────────────────────────────────────────────
// Recibe data.label, data.color, data.description (del registro de node_types).

function FlowNode({ data }) {
  return (
    <div
      title={data.description}
      style={{
        background: data.color,
        color: '#fff',
        borderRadius: 8,
        border: 'none',
        padding: '8px 16px',
        fontSize: 13,
        cursor: 'default',
        whiteSpace: 'nowrap',
      }}
    >
      <Handle type="target" position={Position.Top}    style={{ opacity: 0 }} />
      {data.label}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
}

const NODE_TYPES_RF = { flowNode: FlowNode }

// ─── Layout con dagre ─────────────────────────────────────────────────────────

const NODE_WIDTH  = 150
const NODE_HEIGHT = 40

function applyDagreLayout(rawNodes, rawEdges, typeMap) {
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
    const pos  = g.node(n.id)
    const meta = typeMap[n.type] || typeMap['generic'] || {}
    return {
      id:   n.id,
      type: 'flowNode',
      data: {
        label:       n.label,
        color:       meta.color       || '#1e293b',
        description: meta.description || '',
      },
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    }
  })

  const edges = rawEdges.map((e, i) => ({
    id:         `e${i}`,
    source:     e.source,
    target:     e.target,
    label:      e.label || undefined,
    style:      { stroke: '#64748b' },
    labelStyle: { fill: '#94a3b8', fontSize: 11 },
  }))

  return { nodes, edges }
}

// ─── FlowCanvas ───────────────────────────────────────────────────────────────

export default function FlowCanvas({ empresaId, apiCall }) {
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => {
    setLoading(true)
    setError(null)

    // Cargamos node-types y grafo en paralelo
    Promise.all([
      apiCall('GET', '/flow/node-types'),
      apiCall('GET', `/empresas/${empresaId}/flow/graph`),
    ])
      .then(([nodeTypesList, graph]) => {
        if (!graph?.nodes) { setError('Respuesta inválida del servidor'); return }

        // Construir mapa tipo_id → { color, description }
        const typeMap = Object.fromEntries(
          (nodeTypesList || []).map(t => [t.id, t])
        )

        const { nodes: n, edges: e } = applyDagreLayout(graph.nodes, graph.edges, typeMap)
        setNodes(n)
        setEdges(e)
      })
      .catch(() => setError('Error al cargar el grafo'))
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
        nodeTypes={NODE_TYPES_RF}
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
