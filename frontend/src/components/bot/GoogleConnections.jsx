/**
 * Conexiones Google Sheets de una bot: listado + modal de alta
 * (cuenta Pulpo compartida o cuenta de servicio propia).
 */
import { useState, useEffect } from 'react'

const PULPO_EMAIL = 'pulpo-sheets@booming-monitor-459317-d3.iam.gserviceaccount.com'

export function GoogleSetupModal({ botId, apiCall, onClose, onSaved }) {
  const [tab, setTab] = useState('pulpo')       // 'pulpo' | 'propia'
  const [jsonText, setJsonText] = useState('')
  const [label, setLabel] = useState('')
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSavePulpo() {
    setSaving(true)
    try {
      await apiCall('POST', `/bots/${botId}/google-connections`, {
        credentials_json: '__pulpo_default__',
        label: 'Cuenta Pulpo',
      }).catch(() => null)
      // pulpo-default ya existe y es global: no necesita POST, simplemente cerramos
      onSaved?.()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  async function handleSavePropia(e) {
    e.preventDefault()
    setErr('')
    let parsed
    try { parsed = JSON.parse(jsonText) } catch { setErr('JSON inválido'); return }
    if (!parsed.client_email || !parsed.private_key) {
      setErr('El JSON debe tener client_email y private_key')
      return
    }
    setSaving(true)
    const res = await apiCall('POST', `/bots/${botId}/google-connections`, {
      credentials_json: jsonText,
      label: label || parsed.client_email.split('@')[0],
    }).catch(() => null)
    setSaving(false)
    if (!res?.ok) { setErr(res?.detail || 'Error al guardar'); return }
    onSaved?.()
    onClose()
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <strong>Agregar cuenta Google Sheets</strong>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          <button
            className={tab === 'pulpo' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setTab('pulpo')}
          >Usar cuenta Pulpo</button>
          <button
            className={tab === 'propia' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setTab('propia')}
          >Cuenta propia</button>
        </div>

        {tab === 'pulpo' && (
          <div>
            <p style={{ fontSize: 14, marginBottom: 12, color: '#374151' }}>
              La cuenta de servicio de Pulpo puede escribir en tu hoja.
              Solo necesitás compartirla como <strong>Editor</strong>.
            </p>
            <div style={{ background: '#f1f5f9', borderRadius: 8, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <span style={{ fontSize: 13, fontFamily: 'monospace', flex: 1 }}>{PULPO_EMAIL}</span>
              <button
                className="btn-ghost btn-sm"
                onClick={() => navigator.clipboard.writeText(PULPO_EMAIL)}
              >Copiar</button>
            </div>
            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 20 }}>
              En tu Google Sheet: <strong>Compartir → pegar el email → Editor → Listo</strong>
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
              <button className="btn-primary btn-sm" onClick={handleSavePulpo} disabled={saving}>
                {saving ? 'Guardando...' : 'Confirmar'}
              </button>
            </div>
          </div>
        )}

        {tab === 'propia' && (
          <form onSubmit={handleSavePropia}>
            <div style={{ fontSize: 13, color: '#374151', marginBottom: 12 }}>
              <strong>Pasos para obtener el JSON:</strong>
              <ol style={{ paddingLeft: 18, marginTop: 6, lineHeight: 1.8 }}>
                <li>console.cloud.google.com → Biblioteca → <em>Google Sheets API</em> → Habilitar</li>
                <li>Credenciales → + Crear credenciales → <em>Cuenta de servicio</em> → Crear</li>
                <li>Clic en la cuenta → Claves → Agregar clave → JSON → se descarga</li>
                <li>Pegá el contenido acá</li>
              </ol>
            </div>
            <textarea
              rows={6}
              value={jsonText}
              onChange={e => setJsonText(e.target.value)}
              placeholder='{"type": "service_account", "client_email": "...", "private_key": "..."}'
              style={{ width: '100%', fontFamily: 'monospace', fontSize: 12, resize: 'vertical', boxSizing: 'border-box' }}
            />
            <input
              type="text"
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="Nombre amigable (opcional)"
              style={{ width: '100%', marginTop: 8, boxSizing: 'border-box' }}
            />
            {err && <div style={{ color: '#c00', fontSize: 13, marginTop: 6 }}>{err}</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button type="button" className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
              <button type="submit" className="btn-primary btn-sm" disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

export function GoogleConnectionsSection({ botId, apiCall, mode, hideAddButton = false }) {
  const [conns, setConns] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    const data = await apiCall('GET', `/bots/${botId}/google-connections`, null).catch(() => [])
    setConns(Array.isArray(data) ? data : [])
    setLoading(false)
  }

  useEffect(() => { load() }, [botId])

  async function handleDelete(conn) {
    if (!confirm(`¿Eliminar conexión "${conn.label}"?`)) return
    await apiCall('DELETE', `/bots/${botId}/google-connections/${conn.id}`, null).catch(() => null)
    load()
  }

  if (loading) return null
  // En modo bot sin google connections: no mostrar nada (el botón está en la sección "Agregar canal")
  if (conns.length === 0 && mode !== 'admin') return null

  return (
    <div>
      <div className="ec-section-label" style={{ background: '#f0fdf4', color: '#15803d' }}>Google Sheets</div>
      {conns.map(conn => (
        <div key={conn.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderBottom: '1px solid #f1f5f9' }}>
          <span style={{ fontSize: 18 }}>📗</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 500, fontSize: 13 }}>{conn.label}</div>
            <div style={{ fontSize: 12, color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{conn.email}</div>
          </div>
          {conn.id === 'pulpo-default' && (
            <span style={{ fontSize: 11, color: '#6b7280', background: '#f1f5f9', borderRadius: 4, padding: '2px 6px' }}>Pulpo</span>
          )}
          {conn.id !== 'pulpo-default' && (
            <button className="btn-danger btn-sm" onClick={() => handleDelete(conn)}>Eliminar</button>
          )}
        </div>
      ))}
      {!hideAddButton && mode === 'admin' && (
        <div className="ec-add-row">
          <button className="btn-sm" style={{ background: '#f0fdf4', color: '#15803d' }} onClick={() => setShowModal(true)}>+ Google Sheets</button>
        </div>
      )}
      {showModal && <GoogleSetupModal botId={botId} apiCall={apiCall} onClose={() => setShowModal(false)} onSaved={load} />}
    </div>
  )
}
