/**
 * Conexiones WhatsApp (wavi) de una bot: listado + picker de sesiones
 * disponibles para asignar (admin).
 */
import { useState, useEffect } from 'react'

export function WaviConnectionsList({ conns, mode, onDelete, onReconnect }) {
  if (conns.length === 0) return null
  return (
    <div>
      <div className="ec-section-label" style={{ background: '#f0fdf4', color: '#15803d' }}>WhatsApp</div>
      {conns.map(conn => (
        <div key={conn.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', fontSize: 13 }}>
          <span style={{ color: conn.status === 'ready' ? '#22c55e' : '#94a3b8' }}>📱</span>
          <span style={{ flex: 1 }}>{conn.number}</span>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>{conn.status || 'stopped'}</span>
          {mode === 'admin' && conn.status !== 'ready' && (
            <button
              title="Reconectar"
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px', fontSize: 14, color: '#15803d', lineHeight: 1 }}
              onClick={() => onReconnect?.(conn.number)}
            >↻</button>
          )}
          {mode === 'admin' && (
            <button className="btn-sm" style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px' }}
              onClick={() => onDelete(conn.number)}>✕</button>
          )}
        </div>
      ))}
    </div>
  )
}

export function WaviSessionPicker({ apiCall, onAssign, onClose }) {
  const [sessions, setSessions] = useState(null)  // null = cargando

  useEffect(() => {
    apiCall('GET', '/wavi/sessions', null)
      .then(s => setSessions(Array.isArray(s) ? s : []))
      .catch(e => { console.warn('[WaviSessionPicker] sesiones', e); setSessions([]) })
  }, [apiCall])

  const loading = sessions === null

  return (
    <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, margin: '8px 16px', padding: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: '#475569' }}>Sesiones Wavi disponibles</div>
      {loading && <div style={{ fontSize: 12, color: '#94a3b8' }}>Cargando…</div>}
      {!loading && sessions.length === 0 && (
        <div style={{ fontSize: 12, color: '#94a3b8' }}>No hay sesiones. Conectá una en Config → Conectar WhatsApp.</div>
      )}
      {!loading && sessions.map(s => (
        <div key={s.session} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ flex: 1, fontSize: 12 }}>
            📱 {s.session}
            {s.authenticated ? <span style={{ color: '#22c55e', marginLeft: 6 }}>✓ conectado</span>
              : <span style={{ color: '#94a3b8', marginLeft: 6 }}>desconectado</span>}
          </span>
          <button className="btn-sm" style={{ background: '#f0fdf4', color: '#15803d' }}
            onClick={() => onAssign(s.session)}>Asignar</button>
        </div>
      ))}
      <button className="btn-sm" style={{ marginTop: 8, color: '#94a3b8' }} onClick={onClose}>Cancelar</button>
    </div>
  )
}
