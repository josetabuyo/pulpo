import { useState, useRef } from 'react'
import { PALETTE_TYPES } from '../store/flowStore.js'

// ─── Tooltip ──────────────────────────────────────────────────────────────────

function NodeTooltip({ nt, anchorEl }) {
  if (!anchorEl) return null
  const rect = anchorEl.getBoundingClientRect()
  const fields = (nt.schema || []).filter(f => f.key)
  return (
    <div style={{
      position: 'fixed',
      top: Math.max(8, rect.top),
      left: rect.right + 10,
      zIndex: 9999,
      width: 260,
      background: 'var(--bg)',
      border: '1px solid var(--border-strong)',
      borderRadius: 8,
      boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      padding: '10px 12px',
      pointerEvents: 'none',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ width: 8, height: 8, borderRadius: 2, background: nt.color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{nt.label}</span>
      </div>
      {nt.description && (
        <div style={{ fontSize: 11, color: 'var(--text-subtle)', lineHeight: 1.5 }}>{nt.description}</div>
      )}
      {nt.help && (
        <div style={{
          fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.6,
          borderTop: '1px solid var(--surface-2)', paddingTop: 6, whiteSpace: 'pre-wrap',
        }}>
          {nt.help}
        </div>
      )}
      {fields.length > 0 && (
        <div style={{ borderTop: '1px solid var(--surface-2)', paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 9, color: 'var(--text-subtle)', fontWeight: 700, letterSpacing: '0.08em' }}>PARÁMETROS</span>
          {fields.map(f => (
            <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontSize: 10, color: 'var(--text)', fontFamily: 'monospace' }}>{f.key}</span>
                <span style={{ fontSize: 9, color: 'var(--text-subtle)' }}>{f.type}</span>
                {f.required && <span style={{ fontSize: 9, color: 'var(--danger)' }}>*</span>}
              </div>
              {(f.hint || f.label) && (
                <span style={{ fontSize: 10, color: 'var(--text-muted)', paddingLeft: 6 }}>{f.hint || f.label}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── NodePalette ──────────────────────────────────────────────────────────────

export default function NodePalette({ typeMap }) {
  const [hoveredId, setHoveredId] = useState(null)
  const [anchorEl, setAnchorEl]   = useState(null)
  const timerRef = useRef(null)

  const allNodes = PALETTE_TYPES
    .map(id => typeMap[id])
    .filter(Boolean)
    .sort((a, b) => a.id.localeCompare(b.id))

  function onDragStart(e, typeId) {
    e.dataTransfer.setData('nodeType', typeId)
    e.dataTransfer.effectAllowed = 'move'
    setHoveredId(null)
    setAnchorEl(null)
  }

  function handleMouseEnter(e, id) {
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setHoveredId(id)
      setAnchorEl(e.currentTarget)
    }, 300)
  }

  function handleMouseLeave() {
    clearTimeout(timerRef.current)
    setHoveredId(null)
    setAnchorEl(null)
  }

  const hoveredNt = hoveredId ? typeMap[hoveredId] : null

  return (
    <>
      <div
        data-testid="node-palette"
        style={{
          width: 160,
          background: 'var(--bg)',
          borderRight: '1px solid var(--surface-2)',
          display: 'flex',
          flexDirection: 'column',
          padding: '12px 6px',
          flexShrink: 0,
        }}
      >
        <div style={{
          fontSize: 10, color: 'var(--border-strong)', fontWeight: 700,
          letterSpacing: '0.1em', marginBottom: 8, paddingLeft: 4,
        }}>
          NODOS
        </div>

        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {allNodes.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-subtle)', padding: '8px 4px' }}>Cargando…</div>
          )}
          {allNodes.map(nt => (
            <div
              key={nt.id}
              draggable
              onDragStart={e => onDragStart(e, nt.id)}
              onMouseEnter={e => handleMouseEnter(e, nt.id)}
              onMouseLeave={handleMouseLeave}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                padding: '6px 6px',
                borderRadius: 5,
                cursor: 'grab',
                userSelect: 'none',
                marginBottom: 1,
                background: hoveredId === nt.id ? 'var(--surface-2)' : 'transparent',
              }}
            >
              <div style={{
                width: 7, height: 7, borderRadius: 2,
                background: nt.color, flexShrink: 0,
              }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                <span style={{
                  fontSize: 10, color: 'var(--text-subtle)', fontFamily: 'monospace',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {nt.id}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {hoveredNt && <NodeTooltip nt={hoveredNt} anchorEl={anchorEl} />}
    </>
  )
}
