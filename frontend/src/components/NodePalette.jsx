/**
 * NodePalette — sidebar izquierdo con tipos de nodo arrastrables.
 *
 * Llama GET /api/flow/node-types para obtener label + color de cada tipo.
 * Solo muestra los tipos en PALETTE_TYPES (los que tienen implementación).
 * Al hacer hover muestra un tooltip con descripción, help (docstring) y campos del schema.
 */
import { useState, useRef } from 'react'
import { PALETTE_TYPES } from '../store/flowStore.js'

// ─── Tooltip ──────────────────────────────────────────────────────────────────

function NodeTooltip({ nt, anchorEl }) {
  if (!anchorEl) return null

  const rect = anchorEl.getBoundingClientRect()
  const fields = (nt.schema || []).filter(f => f.type !== 'bool' || f.label)

  return (
    <div
      style={{
        position: 'fixed',
        top: Math.max(8, rect.top),
        left: rect.right + 10,
        zIndex: 9999,
        width: 260,
        background: '#0f172a',
        border: '1px solid #334155',
        borderRadius: 8,
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
        padding: '10px 12px',
        pointerEvents: 'none',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      {/* Nombre + tipo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ width: 8, height: 8, borderRadius: 2, background: nt.color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>{nt.label}</span>
      </div>

      {/* Descripción corta */}
      {nt.description && (
        <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.5 }}>
          {nt.description}
        </div>
      )}

      {/* Docstring */}
      {nt.help && (
        <div style={{ fontSize: 10, color: '#64748b', lineHeight: 1.6, borderTop: '1px solid #1e293b', paddingTop: 6, whiteSpace: 'pre-wrap' }}>
          {nt.help}
        </div>
      )}

      {/* Campos del schema */}
      {fields.length > 0 && (
        <div style={{ borderTop: '1px solid #1e293b', paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 9, color: '#475569', fontWeight: 700, letterSpacing: '0.08em' }}>PARÁMETROS</span>
          {fields.map(f => (
            <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontSize: 10, color: '#cbd5e1', fontFamily: 'monospace' }}>{f.key}</span>
                <span style={{ fontSize: 9, color: '#475569' }}>{f.type}</span>
                {f.required && <span style={{ fontSize: 9, color: '#ef4444' }}>*</span>}
              </div>
              {(f.hint || f.label) && (
                <span style={{ fontSize: 10, color: '#64748b', paddingLeft: 6 }}>
                  {f.hint || f.label}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── NodePalette ──────────────────────────────────────────────────────────────

export default function NodePalette({ apiCall, typeMap }) {
  const paletteNodes = PALETTE_TYPES.map(id => typeMap[id]).filter(Boolean)
  const [hoveredId, setHoveredId] = useState(null)
  const [anchorEl, setAnchorEl] = useState(null)
  const timerRef = useRef(null)

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
      <div style={{
        width: 180,
        background: '#0f172a',
        borderRight: '1px solid #1e293b',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
        padding: '12px 8px',
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, letterSpacing: '0.08em', marginBottom: 10, paddingLeft: 4 }}>
          NODOS
        </div>

        {paletteNodes.length === 0 && (
          <div style={{ fontSize: 12, color: '#475569', padding: '8px 4px' }}>Cargando...</div>
        )}

        {paletteNodes.map(nt => (
          <div
            key={nt.id}
            draggable
            onDragStart={e => onDragStart(e, nt.id)}
            onMouseEnter={e => handleMouseEnter(e, nt.id)}
            onMouseLeave={handleMouseLeave}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '7px 8px',
              borderRadius: 6,
              cursor: 'grab',
              userSelect: 'none',
              marginBottom: 2,
              background: hoveredId === nt.id ? '#1e293b' : 'transparent',
            }}
          >
            <div style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              background: nt.color,
              flexShrink: 0,
            }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <span style={{ fontSize: 11, color: '#cbd5e1', fontFamily: 'monospace' }}>{nt.id}</span>
              <span style={{ fontSize: 10, color: '#475569' }}>{nt.label}</span>
            </div>
          </div>
        ))}

        <div style={{ marginTop: 'auto', paddingTop: 12, borderTop: '1px solid #1e293b' }}>
          <div style={{ fontSize: 10, color: '#334155', lineHeight: 1.5 }}>
            Arrastrá un nodo al canvas para agregarlo
          </div>
        </div>
      </div>

      {hoveredNt && <NodeTooltip nt={hoveredNt} anchorEl={anchorEl} />}
    </>
  )
}
