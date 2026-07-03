import { useRef, useCallback, useState, createContext, useContext } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  MarkerType,
  useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useFlowStore } from '../store/flowStore.js'

// ─── Contexto de modo borrar ──────────────────────────────────────────────────

const EdgeActionsCtx = createContext({ deleteMode: false, deleteEdge: null, updateEdgeBend: null })

// ─── Edge custom ──────────────────────────────────────────────────────────────

function LabeledEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, selected, markerEnd, markerStart, data }) {
  const { deleteMode, deleteEdge, updateEdgeBend } = useContext(EdgeActionsCtx)
  const { screenToFlowPosition } = useReactFlow()
  const [localBend, setLocalBend] = useState(null)

  const bendX = localBend?.x ?? data?.bendX
  const bendY = localBend?.y ?? data?.bendY
  const hasBend = bendX != null && bendY != null

  // ── Path ──────────────────────────────────────────────────────────────────────
  let edgePath, dotX, dotY
  if (hasBend) {
    const bx = bendX, by = bendY
    const R = 10

    if (targetY < by - 10) {
      // Back-edge con bend: source→down→horizontal(bx)→up→horizontal(tx)→down→target
      // El arrowhead siempre entra desde arriba; bendX controla el desvío lateral
      const topY = targetY - 50
      const dv1 = by >= sourceY ? 1 : -1
      const dh1 = bx <= sourceX ? -1 : 1
      const dh2 = targetX >= bx ? 1 : -1
      const r1 = Math.min(R, Math.abs(by - sourceY) / 2, Math.abs(bx - sourceX) / 2 || R)
      const r2 = Math.min(R, Math.abs(bx - sourceX) / 2 || R, Math.abs(by - topY) / 2)
      const r3 = Math.min(R, Math.abs(by - topY) / 2, Math.abs(targetX - bx) / 2 || R)
      const r4 = Math.min(R, Math.abs(targetX - bx) / 2 || R, Math.abs(topY - targetY) / 2)
      edgePath = [
        `M ${sourceX},${sourceY}`,
        `L ${sourceX},${by - dv1 * r1}`,
        `Q ${sourceX},${by} ${sourceX + dh1 * r1},${by}`,
        `L ${bx - dh1 * r2},${by}`,
        `Q ${bx},${by} ${bx},${by - r2}`,
        `L ${bx},${topY + r3}`,
        `Q ${bx},${topY} ${bx + dh2 * r3},${topY}`,
        `L ${targetX - dh2 * r4},${topY}`,
        `Q ${targetX},${topY} ${targetX},${topY + r4}`,
        `L ${targetX},${targetY}`,
      ].join(' ')
      dotX = bx; dotY = by
    } else {
      // Forward edge con bend: vertical → horizontal (bendY) → vertical
      const r = Math.min(R,
        Math.abs(by - sourceY) / 2,
        Math.abs(targetY - by) / 2,
        Math.abs(targetX - sourceX) / 2 || R,
      )
      const dv1 = by >= sourceY ? 1 : -1
      const dv2 = targetY >= by ? 1 : -1
      const dh  = targetX >= sourceX ? 1 : -1
      edgePath = [
        `M ${sourceX},${sourceY}`,
        `L ${sourceX},${by - dv1 * r}`,
        `Q ${sourceX},${by} ${sourceX + dh * r},${by}`,
        `L ${targetX - dh * r},${by}`,
        `Q ${targetX},${by} ${targetX},${by + dv2 * r}`,
        `L ${targetX},${targetY}`,
      ].join(' ')
      dotX = (sourceX + targetX) / 2; dotY = by
    }
  } else {
    const isBackEdge = targetY < sourceY - 20
    const args = isBackEdge
      ? { sourceX, sourceY, sourcePosition: Position.Bottom, targetX, targetY, targetPosition: Position.Top, borderRadius: 16, offset: 50 }
      : { sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 16, offset: 20 }
    ;[edgePath, dotX, dotY] = getSmoothStepPath(args)
  }

  // ── Drag para reubicar el bend point ─────────────────────────────────────────
  const startDrag = useCallback((e) => {
    e.stopPropagation()
    e.preventDefault()
    const startX = e.clientX, startY = e.clientY
    let moved = false
    const onMove = (ev) => {
      if (!moved && Math.abs(ev.clientX - startX) < 3 && Math.abs(ev.clientY - startY) < 3) return
      moved = true
      setLocalBend(screenToFlowPosition({ x: ev.clientX, y: ev.clientY }))
    }
    const onUp = (ev) => {
      if (moved) {
        const { x, y } = screenToFlowPosition({ x: ev.clientX, y: ev.clientY })
        updateEdgeBend?.(id, x, y)
      }
      setLocalBend(null)
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
    }
    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
  }, [id, screenToFlowPosition, updateEdgeBend])

  const removeBend = useCallback((e) => {
    e.stopPropagation()
    updateEdgeBend?.(id, null, null)
  }, [id, updateEdgeBend])

  const onDelete = useCallback((e) => {
    e.stopPropagation()
    deleteEdge?.(id)
  }, [id, deleteEdge])

  const showHandle = !deleteMode && (selected || hasBend)

  return (
    <>
      <BaseEdge
        path={edgePath}
        markerEnd={markerEnd}
        markerStart={markerStart}
        style={{ stroke: deleteMode ? '#ef4444' : selected ? '#94a3b8' : '#475569', strokeWidth: 2, cursor: deleteMode ? 'pointer' : 'default' }}
        onClick={deleteMode ? (e) => { e.stopPropagation(); deleteEdge?.(id) } : undefined}
      />
      <EdgeLabelRenderer>
        <div
          style={{ position: 'absolute', transform: `translate(-50%, -50%) translate(${dotX}px,${dotY}px)`, pointerEvents: 'all', display: 'flex', alignItems: 'center', gap: 4 }}
          className="nodrag nopan"
        >
          {/* Label — drag handle en modo normal */}
          {label && (
            <span
              onPointerDown={!deleteMode ? startDrag : undefined}
              style={{
                background: '#1e293b',
                border: `1px solid ${hasBend && !deleteMode ? '#6366f1' : '#334155'}`,
                borderRadius: 4,
                color: '#94a3b8',
                fontSize: 11,
                padding: '1px 6px',
                whiteSpace: 'nowrap',
                cursor: !deleteMode ? 'grab' : 'default',
                userSelect: 'none',
              }}
            >
              {label}
            </span>
          )}

          {/* Pelotita — edges sin label, visible al seleccionar o cuando hay bend */}
          {!label && showHandle && (
            <div
              onPointerDown={startDrag}
              onDoubleClick={hasBend ? removeBend : undefined}
              title={hasBend ? 'Arrastrá · doble clic para resetear' : 'Arrastrá para doblar la flecha'}
              style={{
                width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                background: hasBend ? '#6366f1' : '#94a3b8',
                border: '2px solid #0f172a',
                cursor: 'grab',
              }}
            />
          )}

          {/* Botón × — solo en modo borrar */}
          {deleteMode && (
            <button
              onClick={onDelete}
              title="Borrar conexión"
              style={{ background: '#7f1d1d', border: 'none', borderRadius: '50%', color: '#fca5a5', width: 18, height: 18, fontSize: 12, cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
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
  const borderColor = data.deleteMode ? '#ef4444' : (data.selected ? '#fff' : 'transparent')

  return (
    <div
      title={data.deleteMode ? 'Clic para eliminar' : data.description}
      onClick={data.deleteMode ? (e) => { e.stopPropagation(); data.onNodeClick?.(id) } : undefined}
      onDoubleClick={!data.deleteMode && data.onDoubleClick ? () => data.onDoubleClick(id) : undefined}
      style={{
        background: data.color,
        color: '#fff',
        borderRadius: 8,
        border: `2px solid ${borderColor}`,
        boxShadow: data.deleteMode ? '0 0 0 2px rgba(239,68,68,0.25)' : 'none',
        width: 160,
        minHeight: 40,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        userSelect: 'none',
        boxSizing: 'border-box',
        padding: '6px 12px',
      }}
    >
      {!isStart && <Handle type="target" position={Position.Top}    style={handleStyle} />}
      <span style={{ fontSize: 13, fontWeight: 500, textAlign: 'center', lineHeight: 1.2 }}>{data.label}</span>
      {!isStart && !isEnd && (
        <span style={{ fontSize: 9, opacity: 0.55, marginTop: 2, fontFamily: 'monospace', letterSpacing: '0.03em' }}>{data.nodeType}</span>
      )}
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
  onEdgeBendChange,
}) {
  const reactFlowWrapper = useRef(null)
  const deleteMode            = useFlowStore(s => s.deleteMode)
  const pendingDeleteNodeId   = useFlowStore(s => s.pendingDeleteNodeId)
  const setPendingDeleteNodeId = useFlowStore(s => s.setPendingDeleteNodeId)
  const deleteNode            = useFlowStore(s => s.deleteNode)

  const deleteEdge = useCallback((edgeId) => {
    onEdgesChange([{ type: 'remove', id: edgeId }])
  }, [onEdgesChange])

  function handleDragOver(e) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const enrichedNodes = (editNodes || []).map(n => ({
    ...n,
    data: {
      ...n.data,
      editable: true,
      deleteMode,
      onDoubleClick: onNodeDoubleClick,
      onNodeClick: (nodeId) => setPendingDeleteNodeId(nodeId),
    },
  }))

  const pendingDeleteNode = pendingDeleteNodeId
    ? (editNodes || []).find(n => n.id === pendingDeleteNodeId)
    : null

  const enrichedEdges = (editEdges || []).map(e => ({
    ...e,
    type: 'labeled',
    markerEnd: { type: MarkerType.ArrowClosed, color: deleteMode ? '#ef4444' : '#475569' },
  }))

  return (
    <EdgeActionsCtx.Provider value={{ deleteMode, deleteEdge, updateEdgeBend: onEdgeBendChange }}>
      <div
        ref={reactFlowWrapper}
        style={{ flex: 1, background: '#0f172a', overflow: 'hidden', position: 'relative' }}
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
          nodesDraggable={!deleteMode}
          nodesConnectable={!deleteMode}
          elementsSelectable
          panOnDrag
          zoomOnScroll
          deleteKeyCode="Delete"
        >
          <Background color="#1e293b" gap={16} />
          <Controls showInteractive={false} style={{ background: '#1e293b', border: '1px solid #334155' }} />
        </ReactFlow>

        {pendingDeleteNode && (
          <div
            style={{
              position: 'absolute',
              top: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 20,
              background: '#1c0a0a',
              border: '1px solid #7f1d1d',
              borderRadius: 8,
              padding: '10px 14px',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
          >
            <span style={{ fontSize: 12, color: '#fca5a5' }}>
              ¿Eliminar <strong>"{pendingDeleteNode.data?.label}"</strong>?
            </span>
            <button
              onClick={() => { deleteNode(pendingDeleteNode.id); setPendingDeleteNodeId(null) }}
              style={{
                padding: '5px 10px',
                background: '#7f1d1d', border: '1px solid #dc2626',
                borderRadius: 5, color: '#fca5a5',
                fontSize: 11, cursor: 'pointer', fontWeight: 600,
              }}
            >
              Sí, eliminar
            </button>
            <button
              onClick={() => setPendingDeleteNodeId(null)}
              style={{
                padding: '5px 10px',
                background: 'transparent', border: '1px solid #334155',
                borderRadius: 5, color: '#64748b',
                fontSize: 11, cursor: 'pointer',
              }}
            >
              Cancelar
            </button>
          </div>
        )}
      </div>
    </EdgeActionsCtx.Provider>
  )
}
