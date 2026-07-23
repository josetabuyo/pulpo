import { useState, useRef, useEffect, useCallback } from 'react'
import { useFlowStore, PALETTE_TYPES } from '../store/flowStore.js'
import ConfigForm from './nodeconfig/ConfigForm.jsx'
import JsonNodeEditor from './nodeconfig/JsonNodeEditor.jsx'

// Variables globales del flow — documentadas en el editor JSON cuando no hay
// ningún nodo seleccionado. "color" solo tiene efecto en flows reutilizables
// (flow_kind === 'node_flow'): pisa el color del nodo `nodo_flow` que invoque
// este flow al elegirlo (ver ConfigForm.jsx y business/flows.py::list_node_flows).
// Referencia estable — el selector de zustand no debe devolver un objeto
// literal nuevo en cada llamada (`s.meta.variables || {}`) o el `{}` cambia
// de identidad en cada notificación del store, gatillando un loop infinito
// de re-render ("Maximum update depth exceeded").
const EMPTY_VARIABLES = {}

const NODE_FLOW_VARIABLES_SCHEMA = [
  {
    key: 'color',
    type: 'string',
    hint: 'Color RGB/hex (ej: var(--tg)) que tomará el nodo "Sub-flow" en otros '
        + 'flows al elegir este flow como sub-flow.',
  },
]

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
        background: 'var(--bg)',
        border: '1px solid var(--border-strong)',
        borderRadius: 8,
        boxShadow: '0 12px 40px rgba(0,0,0,0.7)',
        overflow: 'hidden',
      }}
    >
      {/* Search */}
      <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--surface-2)' }}>
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
            background: 'var(--surface-2)',
            border: '1px solid var(--border-strong)',
            borderRadius: 5,
            color: 'var(--text)',
            outline: 'none',
            fontFamily: 'inherit',
          }}
        />
      </div>

      {/* Node list */}
      <div style={{ maxHeight: 280, overflowY: 'auto' }}>
        {allNodes.length === 0 && (
          <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-subtle)' }}>Cargando…</div>
        )}
        {allNodes.length > 0 && filtered.length === 0 && (
          <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-subtle)' }}>Sin resultados</div>
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
                color: 'var(--text)',
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
              borderBottom: '1px solid var(--border)',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
            onMouseLeave={e => e.currentTarget.style.background = ''}
          >
            <div style={{
              width: 9, height: 9, borderRadius: 2,
              background: nt.color, flexShrink: 0,
            }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
              <span style={{
                fontSize: 12, color: 'var(--text)', fontFamily: 'monospace',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {nt.id}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-subtle)' }}>{nt.label}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── NodeConfigPanel ──────────────────────────────────────────────────────────

const MIN_PANEL_WIDTH = 280
const MAX_PANEL_WIDTH = 720
const DEFAULT_PANEL_WIDTH = 400

export default function NodeConfigPanel({ botId, flowId, flowKind, connections, apiCall, onGoToUIs, onAddNode, onDuplicateNode, onWidthChange }) {
  const nodes             = useFlowStore(s => s.nodes)
  const typeMap           = useFlowStore(s => s.typeMap)
  const selectedNodeId    = useFlowStore(s => s.selectedNodeId)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const updateNodeLabel   = useFlowStore(s => s.updateNodeLabel)
  const deleteMode        = useFlowStore(s => s.deleteMode)
  const toggleDeleteMode  = useFlowStore(s => s.toggleDeleteMode)
  const flowVariables     = useFlowStore(s => s.meta.variables || EMPTY_VARIABLES)
  const setMeta           = useFlowStore(s => s.setMeta)

  const [showPicker, setShowPicker] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [width, setWidth] = useState(DEFAULT_PANEL_WIDTH)
  const resizingRef = useRef(false)

  useEffect(() => { onWidthChange?.(collapsed ? 36 : width) }, [collapsed, width, onWidthChange])

  const handleResizeStart = useCallback((e) => {
    e.preventDefault()
    resizingRef.current = true
    const startX = e.clientX
    const startWidth = width
    function handleMouseMove(ev) {
      if (!resizingRef.current) return
      const delta = startX - ev.clientX
      setWidth(Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, startWidth + delta)))
    }
    function handleMouseUp() {
      resizingRef.current = false
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }, [width])

  // Doble clic en un nodo (selectedNodeId cambia) → mostrar el panel si estaba escondido
  useEffect(() => {
    if (selectedNodeId) setCollapsed(false)
  }, [selectedNodeId])

  const selectedNode = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null
  const schema       = selectedNode ? (typeMap[selectedNode.data.nodeType]?.schema || []) : []

  function handleAddNode(typeId) {
    if (onAddNode) onAddNode(typeId)
    setShowPicker(false)
  }

  if (collapsed) {
    return (
      <div style={{
        width: 36,
        background: 'var(--bg)',
        borderLeft: '1px solid var(--surface-2)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        flexShrink: 0,
        height: '100%',
        paddingTop: 10,
      }}>
        <button
          onClick={() => setCollapsed(false)}
          title="Mostrar panel de configuración"
          style={{
            width: 24,
            height: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'transparent',
            border: '1px solid var(--border-strong)',
            borderRadius: 6,
            color: 'var(--text-subtle)',
            cursor: 'pointer',
            fontSize: 10,
          }}
        >
          ◀
        </button>
      </div>
    )
  }

  return (
    <div
      onWheel={e => e.stopPropagation()}
      style={{
        position: 'relative',
        width,
        background: 'var(--bg)',
        borderLeft: '1px solid var(--surface-2)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        height: '100%',
        overflowY: 'auto',
      }}>

      {/* ── Resize handle ────────────────────────────────────────────── */}
      <div
        onMouseDown={handleResizeStart}
        title="Arrastrar para redimensionar"
        style={{
          position: 'absolute',
          top: 0,
          left: -3,
          width: 6,
          height: '100%',
          cursor: 'col-resize',
          zIndex: 10,
        }}
      />

      {/* ── Buttons: COLLAPSE + ADD + DELETE ────────────────────────────── */}
      <div style={{
        position: 'relative',
        padding: '10px 12px',
        borderBottom: '1px solid var(--surface-2)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={() => setCollapsed(true)}
            title="Colapsar panel"
            style={{
              width: 28,
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'transparent',
              border: '1px solid var(--border-strong)',
              borderRadius: 6,
              color: 'var(--text-subtle)',
              cursor: 'pointer',
              fontSize: 10,
            }}
          >
            ▶
          </button>

          <button
            onClick={() => { if (deleteMode || !selectedNode) return; onDuplicateNode?.() }}
            disabled={deleteMode || !selectedNode}
            title={selectedNode ? 'Duplicar nodo seleccionado' : 'Seleccioná un nodo para duplicarlo'}
            style={{
              width: 28,
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'transparent',
              border: '1px solid var(--border-strong)',
              borderRadius: 6,
              color: 'var(--text-subtle)',
              cursor: (deleteMode || !selectedNode) ? 'not-allowed' : 'pointer',
              opacity: (deleteMode || !selectedNode) ? 0.4 : 1,
              fontSize: 13,
            }}
          >
            ⧉
          </button>

          <button
            onClick={() => { if (deleteMode) return; setShowPicker(v => !v) }}
            disabled={deleteMode}
            style={{
              flex: 1,
              padding: '7px 10px',
              background: showPicker ? 'rgba(46,166,218,.12)' : 'var(--surface-2)',
              border: `1px solid ${showPicker ? 'var(--tg)' : 'var(--border-strong)'}`,
              borderRadius: 6,
              color: showPicker ? 'var(--tg)' : 'var(--text-subtle)',
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
              background: deleteMode ? 'var(--danger-dim)' : 'transparent',
              border: `1px solid ${deleteMode ? 'var(--danger)' : 'var(--border-strong)'}`,
              borderRadius: 6,
              color: deleteMode ? 'var(--danger)' : 'var(--text-subtle)',
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
          <div
            onWheel={e => e.stopPropagation()}
            style={{
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              padding: '12px 14px',
            }}>
            <span style={{ fontSize: 9, color: 'var(--border-strong)', fontWeight: 700, letterSpacing: '0.12em' }}>
              VARIABLES DEL FLOW
            </span>
            <JsonNodeEditor
              config={flowVariables}
              schema={flowKind === 'node_flow' ? NODE_FLOW_VARIABLES_SCHEMA : []}
              onChange={variables => setMeta({ variables })}
            />
          </div>
        ) : (
          <div
            onWheel={e => e.stopPropagation()}
            style={{
              flex: 1,
              minHeight: 0,
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
              background: selectedNode.data.color || 'var(--surface-2)',
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
