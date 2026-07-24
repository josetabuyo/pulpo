/**
 * Conexiones WhatsApp (wavi) de una bot: listado + picker de sesiones
 * disponibles para asignar (admin).
 */
import { useState, useEffect } from 'react'

export function WaviConnectionsList({ conns, mode, onDelete, onReconnect }) {
  if (conns.length === 0) return null
  return (
    <div>
      <div className="ec-section-label" style={{ background: 'var(--success-dim)', color: 'var(--success)' }}>WhatsApp</div>
      {conns.map(conn => (
        <div key={conn.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', fontSize: 13 }}>
          <span style={{ color: conn.status === 'ready' ? 'var(--success)' : 'var(--text-subtle)' }}>📱</span>
          <span style={{ flex: 1 }}>{conn.alias || conn.number}</span>
          <span style={{ fontSize: 11, color: conn.status === 'ready' ? 'var(--success)' : conn.status === 'connecting' ? 'var(--warning)' : 'var(--text-subtle)' }}>
            {conn.status || 'stopped'}
          </span>
          {mode === 'admin' && conn.status !== 'ready' && (
            <button
              title={conn.status === 'disconnected' ? 'Reconectar WhatsApp' : 'Conectar WhatsApp'}
              style={{
                background: 'var(--success-dim)',
                border: '1px solid var(--success)',
                borderRadius: 4,
                cursor: 'pointer',
                padding: '2px 8px',
                fontSize: 12,
                color: 'var(--success)',
                fontWeight: 500,
                whiteSpace: 'nowrap',
              }}
              disabled={conn.status === 'connecting'}
              onClick={() => onReconnect?.(conn.number)}
            >
              {conn.status === 'connecting' ? '⏳ Conectando…' : conn.status === 'disconnected' ? '↻ Reconectar' : '▶ Conectar'}
            </button>
          )}
          {mode === 'admin' && (
            <button className="btn-sm" style={{ color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px' }}
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
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, margin: '8px 16px', padding: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-muted)' }}>Sesiones Wavi disponibles</div>
      {loading && <div style={{ fontSize: 12, color: 'var(--text-subtle)' }}>Cargando…</div>}
      {!loading && sessions.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-subtle)' }}>No hay sesiones. Conectá una en Config → Conectar WhatsApp.</div>
      )}
      {!loading && sessions.map(s => (
        <div key={s.session} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ flex: 1, fontSize: 12 }}>
            📱 {s.session}
            {s.authenticated ? <span style={{ color: 'var(--success)', marginLeft: 6 }}>✓ conectado</span>
              : <span style={{ color: 'var(--text-subtle)', marginLeft: 6 }}>desconectado</span>}
          </span>
          <button className="btn-sm" style={{ background: 'var(--success-dim)', color: 'var(--success)' }}
            onClick={() => onAssign(s.session)}>Asignar</button>
        </div>
      ))}
      <button className="btn-sm" style={{ marginTop: 8, color: 'var(--text-subtle)' }} onClick={onClose}>Cancelar</button>
    </div>
  )
}
