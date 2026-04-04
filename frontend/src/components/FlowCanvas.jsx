import { useEffect, useState, useRef } from 'react'
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

// ─── Nodo custom ──────────────────────────────────────────────────────────────
// data.editable = true  → handles visibles + cursor pointer (modo editor)
// data.editable = false → handles ocultos + cursor default (modo vista)

function FlowNode({ id, data }) {
  const showHandles = !!data.editable
  const isStart = data.nodeType === 'start'
  const isEnd   = data.nodeType === 'end'

  const handleStyle = showHandles
    ? { background: '#64748b', width: 8, height: 8, border: '2px solid #0f172a' }
    : { opacity: 0 }

  return (
    <div
      title={data.description}
      onDoubleClick={data.onDoubleClick ? () => data.onDoubleClick(id) : undefined}
      style={{
        background: data.color,
        color: '#fff',
        borderRadius: 8,
        border: data.selected ? '2px solid #fff' : '2px solid transparent',
        padding: '8px 16px',
        fontSize: 13,
        cursor: showHandles ? 'pointer' : 'default',
        whiteSpace: 'nowrap',
        minWidth: 120,
        textAlign: 'center',
        userSelect: 'none',
      }}
    >
      {!isStart && (
        <Handle type="target" position={Position.Top}    style={handleStyle} />
      )}
      {data.label}
      {!isEnd && (
        <Handle type="source" position={Position.Bottom} style={handleStyle} />
      )}
    </div>
  )
}

const NODE_TYPES_RF = { flowNode: FlowNode }

// ─── Layout con dagre (solo para modo vista) ──────────────────────────────────

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
        editable:    false,
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
//
// Modo vista  (por defecto): recibe empresaId + apiCall, carga y muestra read-only
// Modo editor (editable=true): recibe nodes/edges/callbacks del padre (FlowEditor)

export default function FlowCanvas({
  // Modo vista
  empresaId,
  apiCall,
  // Modo editor
  editable = false,
  nodes: editNodes,
  edges: editEdges,
  onNodesChange: editOnNodesChange,
  onEdgesChange: editOnEdgesChange,
  onConnect: editOnConnect,
  onNodeDoubleClick,
  onDrop: externalOnDrop,
}) {
  // ── Estado modo vista ──
  const [loading, setLoading] = useState(!editable)
  const [error,   setError]   = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // Modo vista: carga datos del servidor
  useEffect(() => {
    if (editable) return
    setLoading(true)
    setError(null)

    Promise.all([
      apiCall('GET', '/flow/node-types'),
      apiCall('GET', `/empresas/${empresaId}/flow/graph`),
    ])
      .then(([nodeTypesList, graph]) => {
        if (!graph?.nodes) { setError('Respuesta inválida del servidor'); return }
        const typeMap = Object.fromEntries((nodeTypesList || []).map(t => [t.id, t]))
        const { nodes: n, edges: e } = applyDagreLayout(graph.nodes, graph.edges, typeMap)
        setNodes(n)
        setEdges(e)
      })
      .catch(() => setError('Error al cargar el grafo'))
      .finally(() => setLoading(false))
  }, [empresaId, editable])

  // ── Drag-over para el modo editor ──
  const reactFlowWrapper = useRef(null)

  function handleDragOver(e) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  // ── Nodos con callback de doble clic inyectado en data ──
  // (React Flow no expone onNodeDoubleClick directamente en el nodo custom)
  const enrichedNodes = editable
    ? (editNodes || []).map(n => ({
        ...n,
        data: { ...n.data, editable: true, onDoubleClick: onNodeDoubleClick },
      }))
    : nodes

  if (!editable && loading) {
    return <div className="empty" style={{ padding: '32px 20px' }}>Cargando flow...</div>
  }
  if (!editable && error) {
    return <div className="empty" style={{ padding: '32px 20px', color: '#ef4444' }}>{error}</div>
  }

  return (
    <div
      ref={reactFlowWrapper}
      style={{ flex: 1, background: '#0f172a', overflow: 'hidden', minHeight: editable ? 0 : 360, borderRadius: editable ? 0 : 8 }}
      onDrop={editable ? externalOnDrop : undefined}
      onDragOver={editable ? handleDragOver : undefined}
    >
      <ReactFlow
        nodes={enrichedNodes}
        edges={editable ? (editEdges || []) : edges}
        nodeTypes={NODE_TYPES_RF}
        onNodesChange={editable ? editOnNodesChange : onNodesChange}
        onEdgesChange={editable ? editOnEdgesChange : onEdgesChange}
        onConnect={editable ? editOnConnect : undefined}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={editable}
        nodesConnectable={editable}
        elementsSelectable={editable}
        panOnDrag={true}
        zoomOnScroll={true}
        deleteKeyCode={editable ? 'Delete' : null}
      >
        <Background color="#1e293b" gap={16} />
        <Controls showInteractive={false} style={{ background: '#1e293b', border: '1px solid #334155' }} />
      </ReactFlow>
    </div>
  )
}
