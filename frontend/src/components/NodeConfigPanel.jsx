import { useState, useRef } from 'react'
import { useFlowStore, PALETTE_TYPES } from '../store/flowStore.js'
import ConfigForm from './nodeconfig/ConfigForm.jsx'

// ─── Node picker popup ────────────────────────────────────────────────────────

function NodePicker({ typeMap, onSelect, onClose, onStartDrag }) {
  const [query, setQuery] = useState('')
  const [locked, setLocked] = useState(true)
  const inputRef = useRef(null)

  const allNodes = PALETTE_TYPES
    .map(id => typeMap[id])
    .filter(Boolean)
    .sort((a, b) => a.id.localeCompare(b.id))

  const q = query.trim().toLowerCase()
  const filtered = q
    ? allNodes.filter(nt =>
        nt.id.toLowerCase().includes(q) ||
        nt.label.toLowerCase().includes(q) ||
        (nt.description || '').toLowerCase().includes(q)
      )
    : allNodes

  // Close on outside click
  const wrapRef = useRef(null)

  return (
    <div
      ref={wrapRef}
      data-testid="node-picker"
      style={{
        position: 'absolute',
        top: 'calc(100% + 4px)',
        left: 0,
        right: 0,
        zIndex: 400,
        background: '#0f172a',
        border: '1px solid #334155',
        borderRadius: 8,
        boxShadow: '0 12px 40px rgba(0,0,0,0.7)',
        overflow: 'hidden',
      }}
    >
      {/* Search */}
      <div style={{ padding: '8px 10px', borderBottom: '1px solid #1e293b' }}>
        <input
          ref={inputRef}
          id="node-picker-search"
          type="search"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck="false"
          name="x_picker_k9m2"
          placeholder="Buscar nodo..."
          data-1p-ignore="true"
          data-lpignore="true"
          data-form-type="other"
          readOnly={locked}
          onFocus={() => setLocked(false)}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => {
            e.stopPropagation()
            if (e.key === 'Escape') onClose()
          }}
          autoFocus
          style={{
            width: '100%',
            boxSizing: 'border-box',
            padding: '5px 8px',
            fontSize: 11,
            background: '#1e293b',
            border: '1px solid #334155',
            borderRadius: 5,
            color: '#cbd5e1',
            outline: 'none',
            fontFamily: 'inherit',
          }}
        />
      </div>

      {/* Node list */}
      <div style={{ maxHeight: 280, overflowY: 'auto' }}>
        {allNodes.length === 0 && (
          <div style={{ padding: '10px 12px', fontSize: 12, color: '#475569' }}>Cargando…</div>
        )}
        {allNodes.length > 0 && filtered.length === 0 && (
          <div style={{ padding: '10px 12px', fontSize: 12, color: '#475569' }}>Sin resultados</div>
        )}
        {filtered.map(nt => (
          <div
            key={nt.id}
            draggable
            onClick={() => onSelect(nt.id)}
            onDragStart={e => {
              e.dataTransfer.setData('nodeType', nt.id)
              e.dataTransfer.effectAllowed = 'move'
              // Ghost en posición del cursor para que el browser compute el layout
              const ghost = document.createElement('div')
              Object.assign(ghost.style, {
                position: 'fixed',
                top: `${e.clientY - 14}px`,
                left: `${e.clientX - 60}px`,
                zIndex: '9999',
                padding: '5px 12px',
                background: nt.color + '33',
                border: `1.5px solid ${nt.color}`,
                borderRadius: '6px',
                color: '#e2e8f0',
                fontSize: '12px',
                fontFamily: 'monospace',
                whiteSpace: 'nowrap',
                pointerEvents: 'none',
                boxShadow: '0 4px 12px rgba(0,0,0,0.6)',
              })
              ghost.textContent = nt.id
              document.body.appendChild(ghost)
              e.dataTransfer.setDragImage(ghost, 60, 14)
              requestAnimationFrame(() => document.body.removeChild(ghost))
            }}
            onDragEnd={() => onStartDrag?.()}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 12px',
              cursor: 'grab',
              borderBottom: '1px solid #0d1929',
            }}
            onMouseEnter={e => e.currentTarget.style.background = '#1e293b'}
            onMouseLeave={e => e.currentTarget.style.background = ''}
          >
            <div style={{
              width: 9, height: 9, borderRadius: 2,
              background: nt.color, flexShrink: 0,
            }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
              <span style={{
                fontSize: 12, color: '#e2e8f0', fontFamily: 'monospace',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {nt.id}
              </span>
              <span style={{ fontSize: 10, color: '#475569' }}>{nt.label}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── NodeConfigPanel ──────────────────────────────────────────────────────────

export default function NodeConfigPanel({ botId, flowId, connections, apiCall, onGoToUIs, onAddNode }) {
  const nodes             = useFlowStore(s => s.nodes)
  const typeMap           = useFlowStore(s => s.typeMap)
  const selectedNodeId    = useFlowStore(s => s.selectedNodeId)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const updateNodeLabel   = useFlowStore(s => s.updateNodeLabel)
  const deleteMode        = useFlowStore(s => s.deleteMode)
  const toggleDeleteMode  = useFlowStore(s => s.toggleDeleteMode)

  const [showPicker, setShowPicker] = useState(false)

  const selectedNode = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null
  const schema       = selectedNode ? (typeMap[selectedNode.data.nodeType]?.schema || []) : []

  function handleAddNode(typeId) {
    if (onAddNode) onAddNode(typeId)
    setShowPicker(false)
  }

  return (
    <div style={{
      width: 400,
      background: '#0b1120',
      borderLeft: '1px solid #1e293b',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      height: '100%',
      overflowY: 'auto',
    }}>

      {/* ── Buttons: ADD + DELETE ──────────────────────────────────────── */}
      <div style={{
        position: 'relative',
        padding: '10px 12px',
        borderBottom: '1px solid #1e293b',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={() => { if (deleteMode) return; setShowPicker(v => !v) }}
            disabled={deleteMode}
            style={{
              flex: 1,
              padding: '7px 10px',
              background: showPicker ? '#162032' : '#1e293b',
              border: `1px solid ${showPicker ? '#3b82f6' : '#334155'}`,
              borderRadius: 6,
              color: showPicker ? '#60a5fa' : '#94a3b8',
              fontSize: 12,
              fontWeight: 600,
              cursor: deleteMode ? 'not-allowed' : 'pointer',
              opacity: deleteMode ? 0.4 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 5,
              transition: 'all 0.15s',
            }}
          >
            <span style={{ fontSize: 16, lineHeight: 1, fontWeight: 300 }}>{showPicker ? '−' : '+'}</span>
            Nuevo nodo
          </button>

          <button
            onClick={() => { toggleDeleteMode(); setShowPicker(false) }}
            title={deleteMode ? 'Salir del modo eliminar' : 'Activar modo eliminar'}
            style={{
              padding: '7px 12px',
              background: deleteMode ? '#7f1d1d' : 'transparent',
              border: `1px solid ${deleteMode ? '#ef4444' : '#334155'}`,
              borderRadius: 6,
              color: deleteMode ? '#fca5a5' : '#94a3b8',
              fontSize: 11,
              cursor: 'pointer',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              transition: 'all 0.15s',
            }}
          >
            🗑 Eliminar
          </button>
        </div>

        {/* Node picker popup */}
        {showPicker && (
          <NodePicker
            typeMap={typeMap}
            onSelect={handleAddNode}
            onClose={() => setShowPicker(false)}
            onStartDrag={() => setShowPicker(false)}
          />
        )}
      </div>

      {/* ── Content area ──────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {!selectedNode ? (
          <div style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#1e293b',
            fontSize: 12,
            textAlign: 'center',
            padding: 24,
            lineHeight: 1.6,
          }}>
            Doble clic en un nodo<br />para configurarlo
          </div>
        ) : (
          <div style={{
            flex: 1,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            padding: '12px 14px',
          }}>
            {/* ── Node chip ────────────────────────────────────── */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: selectedNode.data.color || '#1e293b',
              borderRadius: 8,
              padding: '8px 12px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
              flexShrink: 0,
            }}>
              <input
                value={selectedNode.data.label}
                onChange={e => updateNodeLabel(selectedNode.id, e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#fff',
                  fontWeight: 600,
                  fontSize: 13,
                  outline: 'none',
                  flex: 1,
                  minWidth: 0,
                  fontFamily: 'inherit',
                  textShadow: '0 1px 2px rgba(0,0,0,0.4)',
                }}
                title="Editar nombre del nodo"
              />
              <span style={{
                fontSize: 10,
                color: 'rgba(255,255,255,0.55)',
                fontFamily: 'monospace',
                background: 'rgba(0,0,0,0.25)',
                padding: '2px 6px',
                borderRadius: 4,
                flexShrink: 0,
              }}>
                {selectedNode.data.nodeType}
              </span>
              <button
                onClick={() => setSelectedNodeId(null)}
                style={{
                  background: 'none', border: 'none',
                  color: 'rgba(255,255,255,0.4)',
                  cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: 2,
                  flexShrink: 0,
                }}
                title="Cerrar"
              >
                ×
              </button>
            </div>

            {/* ── Config form ──────────────────────────────────── */}
            <ConfigForm
              node={selectedNode}
              schema={schema}
              botId={botId}
              flowId={flowId}
              connections={connections}
              apiCall={apiCall}
              onGoToUIs={onGoToUIs}
            />
          </div>
        )}
      </div>
    </div>
  )
}
