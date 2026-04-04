/**
 * NodeConfigPanel — panel lateral derecho para configurar el nodo seleccionado.
 *
 * Se muestra cuando selectedNodeId != null.
 * Renderiza un formulario según node.data.nodeType.
 */
import { useFlowStore } from '../store/flowStore.js'

// Formularios por tipo de nodo
function ReplyForm({ config, onChange }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <label style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>MENSAJE</label>
      <textarea
        value={config.message || ''}
        onChange={e => onChange({ ...config, message: e.target.value })}
        placeholder="Texto que enviará el bot..."
        rows={6}
        style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: 6,
          color: '#e2e8f0',
          fontSize: 13,
          padding: '8px 10px',
          resize: 'vertical',
          fontFamily: 'inherit',
        }}
      />
    </div>
  )
}

function LlmRespondForm({ config, onChange }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <label style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>PROMPT DEL SISTEMA</label>
      <textarea
        value={config.prompt || ''}
        onChange={e => onChange({ ...config, prompt: e.target.value })}
        placeholder="Instrucciones para el modelo de lenguaje..."
        rows={8}
        style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: 6,
          color: '#e2e8f0',
          fontSize: 13,
          padding: '8px 10px',
          resize: 'vertical',
          fontFamily: 'inherit',
        }}
      />
    </div>
  )
}

function NoConfigForm({ label }) {
  return (
    <div style={{ fontSize: 12, color: '#475569', padding: '8px 0' }}>
      El nodo <strong style={{ color: '#64748b' }}>{label}</strong> no tiene configuración adicional.
    </div>
  )
}

function ConfigForm({ node }) {
  const updateNodeConfig = useFlowStore(s => s.updateNodeConfig)
  const deleteNode = useFlowStore(s => s.deleteNode)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const { nodeType, config, label, color } = node.data

  function handleChange(newConfig) {
    updateNodeConfig(node.id, newConfig)
  }

  function handleDelete() {
    if (nodeType === 'start' || nodeType === 'end') return
    deleteNode(node.id)
  }

  const isSpecial = nodeType === 'start' || nodeType === 'end'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      {/* Header del panel */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 12, height: 12, borderRadius: 3, background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', flex: 1 }}>{label}</span>
        <button
          onClick={() => setSelectedNodeId(null)}
          style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 2 }}
          title="Cerrar"
        >×</button>
      </div>

      <div style={{ borderTop: '1px solid #1e293b', paddingTop: 12 }}>
        {nodeType === 'reply'          && <ReplyForm     config={config} onChange={handleChange} />}
        {nodeType === 'llm_respond'    && <LlmRespondForm config={config} onChange={handleChange} />}
        {(nodeType === 'summarize' || nodeType === 'luganense_flow' || isSpecial) && (
          <NoConfigForm label={label} />
        )}
      </div>

      {!isSpecial && (
        <div style={{ marginTop: 'auto' }}>
          <button
            onClick={handleDelete}
            style={{
              width: '100%',
              padding: '6px 12px',
              background: 'transparent',
              border: '1px solid #7f1d1d',
              borderRadius: 6,
              color: '#ef4444',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Eliminar nodo
          </button>
        </div>
      )}
    </div>
  )
}

export default function NodeConfigPanel() {
  const nodes = useFlowStore(s => s.nodes)
  const selectedNodeId = useFlowStore(s => s.selectedNodeId)

  const selectedNode = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null

  if (!selectedNode) {
    return (
      <div style={{
        width: 220,
        background: '#0f172a',
        borderLeft: '1px solid #1e293b',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 12, color: '#334155', textAlign: 'center', padding: 16 }}>
          Doble clic en un nodo para configurarlo
        </div>
      </div>
    )
  }

  return (
    <div style={{
      width: 220,
      background: '#0f172a',
      borderLeft: '1px solid #1e293b',
      padding: 16,
      flexShrink: 0,
      overflowY: 'auto',
    }}>
      <ConfigForm node={selectedNode} />
    </div>
  )
}
