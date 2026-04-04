import { useRef } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
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
        padding: '8px 16px',
        fontSize: 13,
        cursor: 'pointer',
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

  function handleDragOver(e) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const enrichedNodes = (editNodes || []).map(n => ({
    ...n,
    data: { ...n.data, editable: true, onDoubleClick: onNodeDoubleClick },
  }))

  return (
    <div
      ref={reactFlowWrapper}
      style={{ flex: 1, background: '#0f172a', overflow: 'hidden' }}
      onDrop={externalOnDrop}
      onDragOver={handleDragOver}
    >
      <ReactFlow
        nodes={enrichedNodes}
        edges={editEdges || []}
        nodeTypes={NODE_TYPES_RF}
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
      </ReactFlow>
    </div>
  )
}
