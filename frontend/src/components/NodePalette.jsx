/**
 * NodePalette — sidebar izquierdo con tipos de nodo arrastrables.
 *
 * Llama GET /api/flow/node-types para obtener label + color de cada tipo.
 * Solo muestra los tipos en PALETTE_TYPES (los que tienen implementación).
 */
import { useEffect, useState } from 'react'
import { PALETTE_TYPES } from '../store/flowStore.js'

export default function NodePalette({ apiCall, typeMap }) {
  const paletteNodes = PALETTE_TYPES.map(id => typeMap[id]).filter(Boolean)

  function onDragStart(e, typeId) {
    e.dataTransfer.setData('nodeType', typeId)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
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
          title={nt.description}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '7px 8px',
            borderRadius: 6,
            cursor: 'grab',
            userSelect: 'none',
            marginBottom: 2,
          }}
          onMouseEnter={e => e.currentTarget.style.background = '#1e293b'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          <div style={{
            width: 10,
            height: 10,
            borderRadius: 3,
            background: nt.color,
            flexShrink: 0,
          }} />
          <span style={{ fontSize: 12, color: '#cbd5e1' }}>{nt.label}</span>
        </div>
      ))}

      <div style={{ marginTop: 'auto', paddingTop: 12, borderTop: '1px solid #1e293b' }}>
        <div style={{ fontSize: 10, color: '#334155', lineHeight: 1.5 }}>
          Arrastrá un nodo al canvas para agregarlo
        </div>
      </div>
    </div>
  )
}
