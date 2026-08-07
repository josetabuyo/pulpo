import { useState, useEffect } from 'react'

// Publica la última corrida de test (o una puntual, si se pasa suiteRunId)
// hacia otro ambiente Pulpo conocido -- mismo patrón que FlowSyncModal.jsx.
// El admin_token del ambiente remoto nunca llega acá; este modal solo habla
// con /api/environments/{name}/test-reports de ESTE backend (ver
// lib/business/test-report-publish.ts).
export default function TestReportPublishModal({ open, onClose, apiCall, botId, suiteRunId, onPublished }) {
  const [environments, setEnvironments] = useState([])
  const [envName, setEnvName] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setResult(null)
    setError('')
    apiCall('GET', '/environments', null).then(data => {
      if (Array.isArray(data)) {
        setEnvironments(data)
        if (data.length && !envName) setEnvName(data[0].name)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function handleClose() {
    if (publishing) return
    onClose()
  }

  async function handlePublish() {
    if (!envName) return
    setPublishing(true)
    setError('')
    try {
      const res = await apiCall('POST', `/environments/${encodeURIComponent(envName)}/test-reports`, {
        bot_id: botId,
        suite_run_id: suiteRunId || undefined,
      })
      if (res?.detail) { setError(res.detail); return }
      setResult(res)
      onPublished?.(res)
    } catch {
      setError('Error al publicar el reporte')
    } finally {
      setPublishing(false)
    }
  }

  if (!open) return null

  return (
    <div className="overlay open" onClick={e => e.target === e.currentTarget && handleClose()}>
      <div className="modal" style={{ width: 480, maxWidth: '92vw' }}>
        <button className="modal-close" onClick={handleClose}>✕</button>
        <h3 style={{ marginBottom: 4 }}>Publicar reporte de test</h3>
        <p className="modal-subtitle">
          Manda los resultados de la última corrida a un ambiente Pulpo conocido, para que quede
          disponible en su vista pública de reportes.
        </p>

        {environments.length === 0 ? (
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            No hay ambientes registrados todavía -- agregá uno en el dashboard, sección &ldquo;Ambientes&rdquo;.
          </p>
        ) : (
          <>
            <div className="fg">
              <label>Ambiente</label>
              <select value={envName} onChange={e => { setEnvName(e.target.value); setResult(null) }}>
                {environments.map(env => (
                  <option key={env.id} value={env.name}>{env.name} ({env.base_url})</option>
                ))}
              </select>
            </div>

            {error && (
              <div className="banner banner-danger">
                <span className="banner-icon">⚠</span>
                <span>{error}</span>
              </div>
            )}

            {result && (
              <div className="banner banner-muted">
                <span className="banner-icon">✓</span>
                <span>
                  Publicado en <strong>{result.environment}</strong> — {result.summary?.passed}/{result.summary?.total} pasaron.
                </span>
              </div>
            )}

            <div className="modal-actions">
              <button className="btn-ghost" onClick={handleClose} disabled={publishing}>
                {result ? 'Cerrar' : 'Cancelar'}
              </button>
              <button className="btn-primary" onClick={handlePublish} disabled={publishing}>
                {publishing ? 'Publicando...' : 'Publicar'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
