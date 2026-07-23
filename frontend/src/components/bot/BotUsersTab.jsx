/**
 * Tab "Usuarios" del portal admin: quién puede loguearse con Google a la
 * vista de solo-este-bot (paso 1 de Pulpo PRO/Lite, ver
 * management/HANDOFF_VERCEL_DEEP_MIGRATION.md). Admin-only -- otorgar acceso
 * es una acción de admin, no algo que un usuario scoped pueda hacer sobre sí
 * mismo ni sobre otros.
 */
import { useState, useEffect } from 'react'

export default function BotUsersTab({ botId, apiCall }) {
  const [emails, setEmails] = useState([])
  const [loading, setLoading] = useState(true)
  const [input, setInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState('')

  async function load() {
    setLoading(true)
    const data = await apiCall('GET', `/bots/${botId}/users`, null).catch(() => [])
    setEmails(Array.isArray(data) ? data : [])
    setLoading(false)
  }

  useEffect(() => { load() }, [botId])

  async function handleAdd(e) {
    e.preventDefault()
    setErr('')
    const email = input.trim().toLowerCase()
    if (!email || !email.includes('@')) { setErr('Email inválido'); return }
    setAdding(true)
    const res = await apiCall('POST', `/bots/${botId}/users`, { email }).catch(() => null)
    setAdding(false)
    if (!res?.ok) { setErr(res?.detail || 'Error al agregar'); return }
    setInput('')
    load()
  }

  async function handleRemove(email) {
    if (!confirm(`¿Sacarle el acceso a ${email}?`)) return
    await apiCall('DELETE', `/bots/${botId}/users/${encodeURIComponent(email)}`, null).catch(() => null)
    load()
  }

  return (
    <div className="ec-config-tab">
      <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
        Estos emails de Google pueden entrar a la vista de solo esta bot
        (<code>/bot/{botId}</code>) sin ver el resto del dashboard. Si un
        email tiene acceso a más de una bot, ve todas las que le diste.
      </p>

      {loading && <div className="empty">Cargando...</div>}

      {!loading && emails.length === 0 && (
        <div className="empty" style={{ padding: '12px 0' }}>Nadie tiene acceso todavía.</div>
      )}

      {!loading && emails.map(email => (
        <div key={email} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', borderBottom: '1px solid #f1f5f9' }}>
          <span style={{ fontSize: 18 }}>👤</span>
          <div style={{ flex: 1, minWidth: 0, fontSize: 13, fontFamily: 'monospace' }}>{email}</div>
          <button className="btn-danger btn-sm" onClick={() => handleRemove(email)}>Sacar</button>
        </div>
      ))}

      <form onSubmit={handleAdd} style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <input
          type="email"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="nombre@gmail.com"
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn-primary btn-sm" disabled={adding}>
          {adding ? 'Agregando...' : '+ Dar acceso'}
        </button>
      </form>
      {err && <div style={{ color: '#c00', fontSize: 13, marginTop: 6 }}>{err}</div>}
    </div>
  )
}
