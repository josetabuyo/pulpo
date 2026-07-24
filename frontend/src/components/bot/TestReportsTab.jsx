import { useState, useEffect, useCallback } from 'react'

// Tab "Test" — lista de reportes HTML de corridas e2e (scripts/generate_e2e_report.py,
// subidos a la tabla test_reports vía lib/business/test-reports.ts) de este bot.
// Uno solo por flow (el script hace upsert por slug) -- hoy Luganense tiene
// uno, pero la lista ya soporta N si otro flow/bot suma el suyo.
function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-AR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function TestReportsTab({ botId, apiCall }) {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiCall('GET', `/bots/${botId}/test-reports`, null).catch(() => null)
      if (Array.isArray(data)) setReports(data)
    } finally {
      setLoading(false)
    }
  }, [botId, apiCall])

  useEffect(() => { load() }, [load])

  if (selected) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{selected.title}</span>
          <button className="btn-ghost btn-sm" onClick={() => setSelected(null)}>← Volver</button>
        </div>
        <iframe
          src={`/api/bots/${botId}/test-reports/${selected.id}`}
          title={selected.title}
          style={{
            width: '100%', height: '80vh', border: '1px solid var(--border)',
            borderRadius: 8, background: '#fff',
          }}
        />
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: 'var(--text-subtle)' }}>
          {reports.length === 0 ? 'Sin reportes de test' : `${reports.length} reporte${reports.length !== 1 ? 's' : ''}`}
        </span>
        <button className="btn-ghost btn-sm" onClick={load}>↺ Actualizar</button>
      </div>

      {loading ? (
        <div className="empty" style={{ padding: '24px 0' }}>Cargando reportes...</div>
      ) : reports.length === 0 ? (
        <div className="empty" style={{ padding: '24px 0' }}>
          Sin reportes de test todavía. Se suben corriendo <code>scripts/generate_e2e_report.py</code>.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {reports.map(r => (
            <div
              key={r.id}
              onClick={() => setSelected(r)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px',
                background: 'var(--bg)', borderRadius: 8, border: '1px solid var(--surface-2)',
                cursor: 'pointer',
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-strong)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-2)'}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{r.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-subtle)', marginTop: 2 }}>
                  Generado {formatDate(r.created_at)}
                </div>
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-subtle)' }}>Ver →</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
