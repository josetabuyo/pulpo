import { useRef, useCallback, useState, createContext, useContext } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  MarkerType,
  useReactFlow,
  Panel,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

// ─── Contexto de modo borrar ──────────────────────────────────────────────────

const DeleteModeCtx = createContext(false)

// ─── Edge custom ──────────────────────────────────────────────────────────────

function LabeledEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, selected }) {
  const { setEdges } = useReactFlow()
  const deleteMode = useContext(DeleteModeCtx)

  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })

  const onDelete = useCallback((e) => {
    e.stopPropagation()
    setEdges(eds => eds.filter(e => e.id !== id))
  }, [id, setEdges])

  return (
    <>
      <BaseEdge
        path={edgePath}
        style={{ stroke: deleteMode ? '#ef4444' : selected ? '#94a3b8' : '#475569', strokeWidth: 2 }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
          className="nodrag nopan"
        >
          {/* Label de ruta — siempre visible si existe */}
          {label && (
            <span style={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 4,
              color: '#94a3b8',
              fontSize: 11,
              padding: '1px 6px',
              whiteSpace: 'nowrap',
            }}>
              {label}
            </span>
          )}

          {/* Botón × — solo en modo borrar */}
          {deleteMode && (
            <button
              onClick={onDelete}
              title="Borrar conexión"
              style={{
                background: '#7f1d1d',
                border: 'none',
                borderRadius: '50%',
                color: '#fca5a5',
                width: 18,
                height: 18,
                fontSize: 12,
                cursor: 'pointer',
                padding: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              ×
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

const EDGE_TYPES = { labeled: LabeledEdge }

// ─── Nodo custom ──────────────────────────────────────────────────────────────

function FlowNode({ id, data }) {
  const isStart = data.nodeType === 'start'
  const isEnd   = data.nodeType === 'end'
  const handleStyle = { background: '#64748b', width: 8, height: 8, border: '2px solid #0f172a' }

  return (
    <div
      title={data.description}
      onDoubleClick={data.onDoubleClick ? () => data.onDoubleClick(id) : undefined}
      style={{
        background: data.color,
        color: '#fff',
        borderRadius: 8,
        border: data.selected ? '2px solid #fff' : '2px solid transparent',
        width: 160,
        height: 40,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 13,
        fontWeight: 500,
        cursor: 'pointer',
        userSelect: 'none',
        boxSizing: 'border-box',
        padding: '0 12px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      {!isStart && <Handle type="target" position={Position.Top}    style={handleStyle} />}
      {data.label}
      {!isEnd   && <Handle type="source" position={Position.Bottom} style={handleStyle} />}
    </div>
  )
}

const NODE_TYPES_RF = { flowNode: FlowNode }

// ─── FlowCanvas ───────────────────────────────────────────────────────────────

export default function FlowCanvas({
  nodes: editNodes,
  edges: editEdges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeDoubleClick,
  onDrop: externalOnDrop,
}) {
  const reactFlowWrapper = useRef(null)
  const [deleteMode, setDeleteMode] = useState(false)

  function handleDragOver(e) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const enrichedNodes = (editNodes || []).map(n => ({
    ...n,
    data: { ...n.data, editable: true, onDoubleClick: onNodeDoubleClick },
  }))

  const enrichedEdges = (editEdges || []).map(e => ({
    ...e,
    type: 'labeled',
    markerEnd: { type: MarkerType.ArrowClosed, color: deleteMode ? '#ef4444' : '#475569' },
  }))

  return (
    <DeleteModeCtx.Provider value={deleteMode}>
      <div
        ref={reactFlowWrapper}
        style={{ flex: 1, background: '#0f172a', overflow: 'hidden' }}
        onDrop={externalOnDrop}
        onDragOver={handleDragOver}
      >
        <ReactFlow
          nodes={enrichedNodes}
          edges={enrichedEdges}
          nodeTypes={NODE_TYPES_RF}
          edgeTypes={EDGE_TYPES}
          defaultEdgeOptions={{ type: 'labeled', markerEnd: { type: MarkerType.ArrowClosed, color: '#475569' } }}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          nodesDraggable
          nodesConnectable
          elementsSelectable
          panOnDrag
          zoomOnScroll
          deleteKeyCode="Delete"
        >
          <Background color="#1e293b" gap={16} />
          <Controls showInteractive={false} style={{ background: '#1e293b', border: '1px solid #334155' }} />
          <Panel position="bottom-right">
            <button
              onClick={() => setDeleteMode(d => !d)}
              title={deleteMode ? 'Salir del modo borrar' : 'Activar modo borrar conexiones'}
              style={{
                background: deleteMode ? '#7f1d1d' : '#1e293b',
                border: `1px solid ${deleteMode ? '#ef4444' : '#334155'}`,
                borderRadius: 6,
                color: deleteMode ? '#fca5a5' : '#64748b',
                fontSize: 16,
                width: 32,
                height: 32,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 4,
              }}
            >
              🗑
            </button>
          </Panel>
        </ReactFlow>
      </div>
    </DeleteModeCtx.Provider>
  )
}
