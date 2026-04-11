/**
 * UIsList — lista de interfaces de usuario disponibles para una empresa.
 *
 * Estructura pensada para crecer: cada entrada en UI_DEFS define
 * una "mini-app" que se puede abrir inline. Por ahora solo existe "Contactos".
 *
 * Props: { botId, apiCall, waConns }
 */
import { useState } from 'react'
import ContactsUI from './ContactsUI.jsx'

const UI_DEFS = [
  {
    id: 'contacts',
    label: 'Contactos',
    icon: '👥',
    description: 'Gestionar contactos, sugeridos y exclusiones del bot.',
    color: '#059669',
  },
]

export default function UIsList({ botId, apiCall, waConns = [] }) {
  const [activeUI, setActiveUI] = useState(null)

  if (activeUI === 'contacts') {
    return (
      <div>
        <button
          className="btn-ghost btn-sm"
          onClick={() => setActiveUI(null)}
          style={{ margin: '8px 16px 0', fontSize: 12 }}
        >
          ← Volver
        </button>
        <ContactsUI botId={botId} apiCall={apiCall} waConns={waConns} />
      </div>
    )
  }

  return (
    <div style={{ padding: '8px 0' }}>
      {UI_DEFS.map(ui => (
        <div
          key={ui.id}
          onClick={() => setActiveUI(ui.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 20px',
            cursor: 'pointer',
            borderBottom: '1px solid #f1f5f9',
            transition: 'background 0.1s',
          }}
          onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          <div style={{
            width: 36, height: 36,
            borderRadius: 8,
            background: ui.color + '20',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 18,
            flexShrink: 0,
          }}>
            {ui.icon}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>{ui.label}</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>{ui.description}</div>
          </div>
          <span style={{ color: '#94a3b8', fontSize: 16 }}>›</span>
        </div>
      ))}
    </div>
  )
}
