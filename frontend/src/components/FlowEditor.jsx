/**
 * FlowEditor — editor visual de un flow.
 *
 * Estructura:
 *   FlowHeader (nombre, connection, contact, guardar)
 *   ├── NodePalette  (izquierda — tipos de nodo arrastrables)
 *   ├── FlowCanvas   (centro — canvas editable)
 *   └── NodeConfigPanel (derecha — config del nodo seleccionado)
 *
 * El estado vive en useFlowStore (Zustand).
 * El padre (FlowList) pasa `flow` con la definición y `onBack` para volver.
 */
import { useEffect, useCallback } from 'react'
import { ReactFlowProvider, useReactFlow } from '@xyflow/react'

import { useFlowStore } from '../store/flowStore.js'
import FlowCanvas     from './FlowCanvas.jsx'
import NodePalette    from './NodePalette.jsx'
import NodeConfigPanel from './NodeConfigPanel.jsx'
import FlowHeader     from './FlowHeader.jsx'

// ─── Inner — necesita estar dentro de ReactFlowProvider para useReactFlow ────

function FlowEditorInner({ flow, connections, apiCall, typeMap, onBack, onSaved }) {
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
  const reset            = useFlowStore(s => s.reset)

  // Cargar el flow y el typeMap en el store al montar
  useEffect(() => {
    setTypeMap(typeMap)
    loadFlow(flow.definition, typeMap)
    return () => reset()
  }, [flow.id])

  // Drop de un nodo desde la paleta
  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const nodeType = e.dataTransfer.getData('nodeType')
    if (!nodeType) return

    const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addNode(nodeType, position)
  }, [screenToFlowPosition, addNode, typeMap])

  // Doble clic en un nodo → abrir panel de config
  const handleNodeDoubleClick = useCallback((nodeId) => {
    setSelectedNodeId(nodeId)
  }, [setSelectedNodeId])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(90vh - 220px)', minHeight: 480 }}>
      <FlowHeader
        flow={flow}
        connections={connections}
        apiCall={apiCall}
        onBack={onBack}
        onSaved={onSaved}
      />
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden', position: 'relative' }}>
        <NodePalette apiCall={apiCall} typeMap={typeMap} />
        <FlowCanvas
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDrop={handleDrop}
          onNodeDoubleClick={handleNodeDoubleClick}
        />
        {/* NodeConfigPanel como popup flotante sobre el canvas */}
        <NodeConfigPanel empresaId={flow.empresa_id} connections={connections} apiCall={apiCall} />
      </div>
    </div>
  )
}

// ─── FlowEditor — wrappea con ReactFlowProvider ───────────────────────────────

export default function FlowEditor({ flow, connections, apiCall, typeMap, onBack, onSaved }) {
  return (
    <ReactFlowProvider>
      <FlowEditorInner
        flow={flow}
        connections={connections}
        apiCall={apiCall}
        typeMap={typeMap}
        onBack={onBack}
        onSaved={onSaved}
      />
    </ReactFlowProvider>
  )
}
