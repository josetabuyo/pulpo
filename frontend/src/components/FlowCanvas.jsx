import { useRef, useCallback, useState, useEffect, createContext, useContext } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  ControlButton,
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

const EdgeActionsCtx = createContext({ deleteMode: false, deleteEdge: null, updateEdgeBend: null, updateEdgeLabel: null, getNodeRoutes: null })

// ─── Edge custom ──────────────────────────────────────────────────────────────

function LabeledEdge({ id, source, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, selected, markerEnd, markerStart, data }) {
  const { deleteMode, deleteEdge, updateEdgeBend, updateEdgeLabel, getNodeRoutes } = useContext(EdgeActionsCtx)
  const { screenToFlowPosition } = useReactFlow()
  const [localBend, setLocalBend] = useState(null)
  const [editing, setEditing] = useState(false)
  const routes = getNodeRoutes?.(source) || []

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
      } else if (updateEdgeLabel) {
        setEditing(true)
      }
      setLocalBend(null)
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
    }
    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
  }, [id, screenToFlowPosition, updateEdgeBend, updateEdgeLabel])

  const removeBend = useCallback((e) => {
    e.stopPropagation()
    updateEdgeBend?.(id, null, null)
  }, [id, updateEdgeBend])

  const onDelete = useCallback((e) => {
    e.stopPropagation()
    deleteEdge?.(id)
  }, [id, deleteEdge])

  const showHandle = !deleteMode && (selected || hasBend || (!label && routes.length > 0))

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

          {/* Pelotita — edges sin label, visible al seleccionar, con bend, o si el nodo origen tiene rutas configurables */}
          {!label && showHandle && (
            <div
              onPointerDown={startDrag}
              onDoubleClick={hasBend ? removeBend : undefined}
              title={routes.length ? 'Clic para asignar ruta · arrastrá para doblar la flecha' : (hasBend ? 'Arrastrá · doble clic para resetear' : 'Arrastrá para doblar la flecha')}
              style={{
                width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                background: routes.length ? '#f59e0b' : (hasBend ? '#6366f1' : '#94a3b8'),
                border: '2px solid #0f172a',
                cursor: 'grab',
              }}
            />
          )}

          {/* Editor de label — dropdown con las rutas del nodo origen (router/condition) o texto libre */}
          {editing && (
            <div
              className="nodrag nopan"
              style={{
                position: 'absolute',
                bottom: '100%',
                left: '50%',
                transform: 'translateX(-50%)',
                marginBottom: 6,
                background: '#1e293b',
                border: '1px solid #6366f1',
                borderRadius: 6,
                padding: 4,
                zIndex: 50,
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
              }}
            >
              {routes.length > 0 ? (
                <select
                  autoFocus
                  defaultValue={label || ''}
                  onChange={(e) => { updateEdgeLabel(id, e.target.value); setEditing(false) }}
                  onBlur={() => setEditing(false)}
                  style={{ fontSize: 11, background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: 4, padding: '2px 4px' }}
                >
                  <option value="">(sin label)</option>
                  {routes.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              ) : (
                <input
                  autoFocus
                  defaultValue={label || ''}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { updateEdgeLabel(id, e.currentTarget.value); setEditing(false) }
                    if (e.key === 'Escape') setEditing(false)
                  }}
                  onBlur={(e) => { updateEdgeLabel(id, e.target.value); setEditing(false) }}
                  style={{ fontSize: 11, width: 110, background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: 4, padding: '2px 4px' }}
                />
              )}
            </div>
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

function FlowNode({ id, data, selected }) {
  const isStart = data.nodeType === 'start'
  const isEnd   = data.nodeType === 'end'
  const handleStyle = { background: '#64748b', width: 8, height: 8, border: '2px solid #0f172a' }
  const isDanger = data.deleteMode || data.pendingDelete
  const borderColor = isDanger ? '#ef4444' : (selected ? '#22c55e' : 'transparent')

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
        boxShadow: isDanger ? '0 0 0 2px rgba(239,68,68,0.25)' : selected ? '0 0 0 2px rgba(34,197,94,0.25)' : 'none',
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

// ─── Herramienta de canvas: puntero (seleccionar) vs mano (mover) ─────────────
// Mantener espacio apretado activa la mano temporalmente, como en Figma.

function PointerIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M4 2 L4 20 L9 15.5 L12 22 L15 20.5 L12 14 L18 14 Z" />
    </svg>
  )
}

function HandIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="5 9 2 12 5 15" />
      <polyline points="9 5 12 2 15 5" />
      <polyline points="15 19 12 22 9 19" />
      <polyline points="19 9 22 12 19 15" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <line x1="12" y1="2" x2="12" y2="22" />
    </svg>
  )
}

export default function FlowCanvas({
  nodes: editNodes,
  edges: editEdges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeDoubleClick,
  onDrop: externalOnDrop,
  onEdgeBendChange,
  onEdgeLabelChange,
}) {
  const reactFlowWrapper = useRef(null)
  const { getNodes, getEdges } = useReactFlow()
  const [tool, setTool] = useState('select') // 'select' | 'pan'
  const [spaceHeld, setSpaceHeld] = useState(false)
  const [isPanning, setIsPanning] = useState(false)
  const deleteMode            = useFlowStore(s => s.deleteMode)
  const pendingDeleteNodeId   = useFlowStore(s => s.pendingDeleteNodeId)
  const setPendingDeleteNodeId = useFlowStore(s => s.setPendingDeleteNodeId)
  const deleteNode            = useFlowStore(s => s.deleteNode)
  const pendingDeleteNodeIds   = useFlowStore(s => s.pendingDeleteNodeIds)
  const setPendingDeleteNodeIds = useFlowStore(s => s.setPendingDeleteNodeIds)
  const deleteNodes            = useFlowStore(s => s.deleteNodes)

  const deleteEdge = useCallback((edgeId) => {
    onEdgesChange([{ type: 'remove', id: edgeId }])
  }, [onEdgesChange])

  // Delete/Backspace: si hay nodos seleccionados (box select o click), pedir
  // confirmación (se pintan de rojo). Si solo hay edges seleccionadas, borrar directo.
  useEffect(() => {
    if (deleteMode) return
    function handleKeyDown(e) {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
      const target = e.target
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return

      const selectedNodeIds = getNodes().filter(n => n.selected).map(n => n.id)
      if (selectedNodeIds.length) {
        e.preventDefault()
        setPendingDeleteNodeIds(selectedNodeIds)
        return
      }
      const selectedEdgeIds = getEdges().filter(e => e.selected).map(e => e.id)
      if (selectedEdgeIds.length) {
        e.preventDefault()
        onEdgesChange(selectedEdgeIds.map(id => ({ type: 'remove', id })))
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [deleteMode, getNodes, getEdges, onEdgesChange, setPendingDeleteNodeIds])

  function handleDragOver(e) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  // Espacio apretado → mano temporal (se restaura la herramienta anterior al soltar)
  useEffect(() => {
    function isTyping(target) {
      return target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
    }
    function handleKeyDown(e) {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.code === 'Space') {
        e.preventDefault()
        setSpaceHeld(true)
        return
      }
      if (e.key === 'v' || e.key === 'V') setTool('select')
      if (e.key === 'h' || e.key === 'H') setTool('pan')
    }
    function handleKeyUp(e) {
      if (e.code !== 'Space') return
      setSpaceHeld(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
    }
  }, [])

  const panMode = tool === 'pan' || spaceHeld
  const canvasCursor = panMode ? (isPanning ? 'grabbing' : 'grab') : 'default'

  const enrichedNodes = (editNodes || []).map(n => ({
    ...n,
    data: {
      ...n.data,
      editable: true,
      deleteMode,
      pendingDelete: pendingDeleteNodeIds.includes(n.id),
      onDoubleClick: onNodeDoubleClick,
      onNodeClick: (nodeId) => setPendingDeleteNodeId(nodeId),
    },
  }))

  const pendingDeleteNode = pendingDeleteNodeId
    ? (editNodes || []).find(n => n.id === pendingDeleteNodeId)
    : null

  const pendingDeleteNodesList = pendingDeleteNodeIds.length
    ? (editNodes || []).filter(n => pendingDeleteNodeIds.includes(n.id))
    : []

  const enrichedEdges = (editEdges || []).map(e => ({
    ...e,
    type: 'labeled',
    markerEnd: { type: MarkerType.ArrowClosed, color: deleteMode ? '#ef4444' : '#475569' },
  }))

  const getNodeRoutes = useCallback((nodeId) => {
    const node = (editNodes || []).find(n => n.id === nodeId)
    if (!node || !['router', 'condition'].includes(node.data?.nodeType)) return []
    return node.data.config?.routes || []
  }, [editNodes])

  return (
    <EdgeActionsCtx.Provider value={{ deleteMode, deleteEdge, updateEdgeBend: onEdgeBendChange, updateEdgeLabel: onEdgeLabelChange, getNodeRoutes }}>
      <div
        ref={reactFlowWrapper}
        style={{ flex: 1, background: '#0f172a', overflow: 'hidden', position: 'relative', cursor: canvasCursor }}
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
          onMoveStart={(e) => { if (e) setIsPanning(true) }}
          onMoveEnd={() => setIsPanning(false)}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          minZoom={0.1}
          maxZoom={2}
          nodesDraggable={!deleteMode && !panMode}
          nodesConnectable={!deleteMode}
          elementsSelectable={!panMode}
          panOnDrag={panMode ? true : [1, 2]}
          selectionOnDrag={!panMode}
          selectionKeyCode={null}
          multiSelectionKeyCode="Shift"
          zoomOnScroll
          deleteKeyCode={null}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e293b" gap={16} />
          <Controls showInteractive={false} style={{ background: '#1e293b', border: '1px solid #334155' }}>
            <ControlButton
              onClick={() => setTool('select')}
              title="Seleccionar (V)"
              style={{ background: tool === 'select' ? '#334155' : undefined, color: tool === 'select' ? '#e2e8f0' : undefined }}
            >
              <PointerIcon />
            </ControlButton>
            <ControlButton
              onClick={() => setTool('pan')}
              title="Mover el lienzo (mantené espacio para activarlo momentáneamente)"
              style={{ background: tool === 'pan' ? '#334155' : undefined, color: tool === 'pan' ? '#e2e8f0' : undefined }}
            >
              <HandIcon />
            </ControlButton>
          </Controls>
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

        {pendingDeleteNodesList.length > 0 && (
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
              ¿Eliminar <strong>{pendingDeleteNodesList.length}</strong> nodo{pendingDeleteNodesList.length === 1 ? '' : 's'}?
            </span>
            <button
              onClick={() => deleteNodes(pendingDeleteNodeIds)}
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
              onClick={() => setPendingDeleteNodeIds([])}
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
