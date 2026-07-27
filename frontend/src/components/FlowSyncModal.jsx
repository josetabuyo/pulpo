import { useState, useEffect, useCallback } from 'react'

// Sync de UN flow contra otro ambiente Pulpo conocido (management/HANDOFF_PULPO_ENVIRONMENTS_REGISTRY.md).
// El admin_token del ambiente remoto nunca llega acá -- este modal solo habla
// con /api/environments/{name}/diff y /sync de ESTE backend, que resuelve el
// token server-side (ver lib/business/environment-sync.ts).
export default function FlowSyncModal({ open, onClose, apiCall, botId, flowId, onSynced }) {
  const [environments, setEnvironments] = useState([])
  const [envName, setEnvName] = useState('')
  const [direction, setDirection] = useState('pull')
  const [diff, setDiff] = useState(null)
  const [loadingDiff, setLoadingDiff] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setDiff(null)
    setError('')
    apiCall('GET', '/environments', null).then(data => {
      if (Array.isArray(data)) {
        setEnvironments(data)
        if (data.length && !envName) setEnvName(data[0].name)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handleClose = useCallback(() => {
    if (loadingDiff || applying) return
    onClose()
  }, [loadingDiff, applying, onClose])

  async function handleViewDiff() {
    if (!envName) return
    setLoadingDiff(true)
    setError('')
    setDiff(null)
    try {
      const res = await apiCall('POST', `/environments/${encodeURIComponent(envName)}/diff`, {
        bot_id: botId,
        flow_id: flowId,
        direction,
      })
      if (res?.detail) setError(res.detail)
      else setDiff(res)
    } catch {
      setError('Error al obtener el diff')
    } finally {
      setLoadingDiff(false)
    }
  }

  async function handleApply() {
    setApplying(true)
    setError('')
    try {
      const res = await apiCall('POST', `/environments/${encodeURIComponent(envName)}/sync`, {
        bot_id: botId,
        flow_id: flowId,
        direction,
      })
      if (res?.detail) { setError(res.detail); return }
      onSynced?.({ direction, result: res })
      onClose()
    } catch {
      setError('Error al aplicar el sync')
    } finally {
      setApplying(false)
    }
  }

  if (!open) return null

  return (
    <div className="overlay open" onClick={e => e.target === e.currentTarget && handleClose()}>
      <div className="modal" style={{ width: 720, maxWidth: '92vw' }}>
        <button className="modal-close" onClick={handleClose}>✕</button>
        <h3 style={{ marginBottom: 4 }}>Sync con otro ambiente</h3>
        <p className="modal-subtitle">Compará este flow contra otro ambiente Pulpo conocido y elegí qué versión conservar.</p>

        {environments.length === 0 ? (
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            No hay ambientes registrados todavía -- agregá uno en el dashboard, sección &ldquo;Ambientes&rdquo;.
          </p>
        ) : (
          <>
            <div className="fg">
              <label>Ambiente</label>
              <select value={envName} onChange={e => { setEnvName(e.target.value); setDiff(null) }}>
                {environments.map(env => (
                  <option key={env.id} value={env.name}>{env.name} ({env.base_url})</option>
                ))}
              </select>
            </div>

            <div className="fg">
              <label>Dirección</label>
              <div className="direction-picker">
                <button
                  type="button"
                  className={`direction-option ${direction === 'pull' ? 'active' : ''}`}
                  onClick={() => { setDirection('pull'); setDiff(null) }}
                >
                  <span className="direction-option-title"><span className="arrow">←</span> Pull</span>
                  <span className="direction-option-desc">Traer la definición de <strong>{envName || '...'}</strong> hacia local</span>
                </button>
                <button
                  type="button"
                  className={`direction-option ${direction === 'push' ? 'active' : ''}`}
                  onClick={() => { setDirection('push'); setDiff(null) }}
                >
                  <span className="direction-option-title"><span className="arrow">→</span> Push</span>
                  <span className="direction-option-desc">Mandar la definición local hacia <strong>{envName || '...'}</strong></span>
                </button>
              </div>
            </div>

            {error && (
              <div className="banner banner-danger">
                <span className="banner-icon">⚠</span>
                <span>{error}</span>
              </div>
            )}

            {!diff && (
              <button className="btn-primary" onClick={handleViewDiff} disabled={loadingDiff} style={{ width: '100%' }}>
                {loadingDiff ? 'Comparando...' : 'Ver diff'}
              </button>
            )}

            {diff && diff.identical && (
              <div className="banner banner-muted">
                <span className="banner-icon">✓</span>
                <span>El destino ya tiene esta misma definición -- nada para sincronizar.</span>
              </div>
            )}

            {diff && !diff.identical && (
              <>
                <div className="banner banner-warning">
                  <span className="banner-icon">⚠</span>
                  <span>
                    El destino queda <strong>INACTIVO</strong> a propósito tras el sync (evita disparar tráfico real por accidente).
                    La definición anterior del destino se guarda como versión antes de pisarla.
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-muted)' }}>
                      DESTINO ACTUAL <span style={{ color: 'var(--text-subtle)', fontWeight: 400 }}>({diff.target_name})</span>
                    </div>
                    <pre style={{ maxHeight: 320, overflow: 'auto', fontSize: 11, background: 'var(--surface-2)', border: '1px solid var(--border)', padding: 10, borderRadius: 8 }}>
                      {JSON.stringify(diff.target_definition, null, 2)}
                    </pre>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--brand-light)' }}>
                      SE VA A ESCRIBIR <span style={{ color: 'var(--text-subtle)', fontWeight: 400 }}>({diff.source_name})</span>
                    </div>
                    <pre style={{ maxHeight: 320, overflow: 'auto', fontSize: 11, background: 'var(--surface-2)', border: '1px solid var(--brand-dim)', padding: 10, borderRadius: 8 }}>
                      {JSON.stringify(diff.source_definition, null, 2)}
                    </pre>
                  </div>
                </div>
                <div className="modal-actions">
                  <button className="btn-ghost" onClick={handleClose} disabled={applying}>Cancelar</button>
                  <button className="btn-primary" onClick={handleApply} disabled={applying}>
                    {applying ? 'Aplicando...' : `Confirmar ${direction}`}
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
