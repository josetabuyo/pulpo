/**
 * NodeConfigPanel — panel lateral derecho para configurar el nodo seleccionado.
 *
 * Totalmente dinámico: el schema de cada nodo viene del backend via
 * GET /api/flow/node-types → typeMap[nodeType].schema
 *
 * Agregar un nodo nuevo = solo Python. El panel aparece solo.
 *
 * Las piezas viven en components/nodeconfig/:
 *   fields.jsx       — Field dinámico por tipo + isVisible + CopyButton
 *   ConfigForm.jsx   — formulario + acciones por tipo de nodo
 *   SummarizeInfo.jsx / SheetCacheButton.jsx — bloques específicos
 */
import { useFlowStore } from '../store/flowStore.js'
import ConfigForm from './nodeconfig/ConfigForm.jsx'

export default function NodeConfigPanel({ empresaId, flowId, connections, apiCall, onGoToUIs }) {
  const nodes             = useFlowStore(s => s.nodes)
  const typeMap           = useFlowStore(s => s.typeMap)
  const selectedNodeId    = useFlowStore(s => s.selectedNodeId)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const selectedNode      = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null

  if (!selectedNode) return null

  const schema = typeMap[selectedNode.data.nodeType]?.schema || []

  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) setSelectedNodeId(null) }}
      style={{
        position: 'absolute', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.35)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
        pointerEvents: 'all',
      }}
    >
      <div style={{
        width: 420,
        height: '100%',
        background: '#0f172a',
        borderLeft: '1px solid #1e293b',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '-8px 0 32px rgba(0,0,0,0.5)',
        overflowY: 'auto',
        padding: 14,
      }}>
        <ConfigForm
          node={selectedNode}
          schema={schema}
          empresaId={empresaId}
          flowId={flowId}
          connections={connections}
          apiCall={apiCall}
          onGoToUIs={onGoToUIs}
        />
      </div>
    </div>
  )
}
