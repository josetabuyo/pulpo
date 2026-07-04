/**
 * FlowEditor — editor visual de un flow.
 *
 * Estructura:
 *   FlowHeader (nombre, connection, contact, guardar)
 *   ├── FlowCanvas      (centro — canvas editable)
 *   └── NodeConfigPanel (derecha — config del nodo seleccionado)
 *
 * El estado vive en useFlowStore (Zustand).
 * El padre (FlowList) pasa `flow` con la definición y `onBack` para volver.
 */
import { useEffect, useCallback, useMemo } from 'react'
import { ReactFlowProvider, useReactFlow } from '@xyflow/react'

import { useFlowStore, createFlowStore, FlowStoreContext } from '../store/flowStore.js'
import FlowCanvas     from './FlowCanvas.jsx'
import NodeConfigPanel from './NodeConfigPanel.jsx'
import FlowHeader     from './FlowHeader.jsx'

// ─── Inner — necesita estar dentro de ReactFlowProvider para useReactFlow ────

function FlowEditorInner({ flow, connections, apiCall, typeMap, onBack, onSaved, onSavedAs, onGoToUIs }) {
  const { screenToFlowPosition } = useReactFlow()
  const loadFlow         = useFlowStore(s => s.loadFlow)
  const setTypeMap       = useFlowStore(s => s.setTypeMap)
  const nodes            = useFlowStore(s => s.nodes)
  const edges            = useFlowStore(s => s.edges)
  const onNodesChange    = useFlowStore(s => s.onNodesChange)
  const onEdgesChange    = useFlowStore(s => s.onEdgesChange)
  const onConnect        = useFlowStore(s => s.onConnect)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const addNode          = useFlowStore(s => s.addNode)
  const duplicateNode    = useFlowStore(s => s.duplicateNode)
  const selectedNodeId   = useFlowStore(s => s.selectedNodeId)
  const updateEdgeBend   = useFlowStore(s => s.updateEdgeBend)
  const reset            = useFlowStore(s => s.reset)
  const undo             = useFlowStore(s => s.undo)
  const nodeCount        = nodes.length

  // Cargar el flow y el typeMap en el store al montar
  useEffect(() => {
    setTypeMap(typeMap)
    loadFlow(flow.definition, typeMap)
    return () => reset()
  }, [flow.id])

  // Ctrl+Z / Cmd+Z → deshacer
  useEffect(() => {
    function handleKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [undo])

  // Drop desde drag del picker → insertar en posición del cursor
  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const nodeType = e.dataTransfer.getData('nodeType')
    if (!nodeType) return
    addNode(nodeType, screenToFlowPosition({ x: e.clientX, y: e.clientY }))
  }, [screenToFlowPosition, addNode])

  // Click en picker → insertar visible, arriba a la izquierda del panel derecho
  const handleAddNode = useCallback((nodeType) => {
    const offset = (nodeCount % 8) * 25
    const panelWidth = 400
    const pos = screenToFlowPosition({
      x: window.innerWidth - panelWidth - 180 - offset,
      y: 90 + offset,
    })
    addNode(nodeType, pos)
  }, [addNode, nodeCount, screenToFlowPosition])

  // Duplicar el nodo seleccionado → aparece junto al panel, igual que "+ Nuevo nodo"
  const handleDuplicateNode = useCallback(() => {
    if (!selectedNodeId) return
    const offset = (nodeCount % 8) * 25
    const panelWidth = 400
    const pos = screenToFlowPosition({
      x: window.innerWidth - panelWidth - 180 - offset,
      y: 90 + offset,
    })
    duplicateNode(selectedNodeId, pos)
  }, [duplicateNode, selectedNodeId, nodeCount, screenToFlowPosition])

  // Doble clic en un nodo → abrir panel de config
  const handleNodeDoubleClick = useCallback((nodeId) => {
    setSelectedNodeId(nodeId)
  }, [setSelectedNodeId])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 480 }}>
      <FlowHeader
        flow={flow}
        connections={connections}
        apiCall={apiCall}
        onBack={onBack}
        onSaved={onSaved}
        onSavedAs={onSavedAs}
      />
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <FlowCanvas
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDrop={handleDrop}
          onNodeDoubleClick={handleNodeDoubleClick}
          onEdgeBendChange={updateEdgeBend}
        />
        <NodeConfigPanel
          botId={flow.bot_id}
          flowId={flow.id}
          connections={connections}
          apiCall={apiCall}
          onGoToUIs={onGoToUIs}
          onAddNode={handleAddNode}
          onDuplicateNode={handleDuplicateNode}
        />
      </div>
    </div>
  )
}

// ─── FlowEditor — wrappea con ReactFlowProvider ───────────────────────────────

export default function FlowEditor({ flow, connections, apiCall, typeMap, onBack, onSaved, onSavedAs, onGoToUIs }) {
  const store = useMemo(() => createFlowStore(), [])
  return (
    <FlowStoreContext.Provider value={store}>
      <ReactFlowProvider>
        <FlowEditorInner
          flow={flow}
          connections={connections}
          apiCall={apiCall}
          typeMap={typeMap}
          onBack={onBack}
          onSaved={onSaved}
          onSavedAs={onSavedAs}
          onGoToUIs={onGoToUIs}
        />
      </ReactFlowProvider>
    </FlowStoreContext.Provider>
  )
}
