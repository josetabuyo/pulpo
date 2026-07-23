import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api.js'
import BotCard, { normalizeBot } from '../components/BotCard.jsx'

// Portal de "un solo bot" para el rol "scoped" (paso 1 de Pulpo PRO/Lite,
// ver management/HANDOFF_VERCEL_DEEP_MIGRATION.md). El login viejo por
// password de bot (JWT de 30 min, /api/bot/login|me|refresh|logout) nunca
// se portó a web/ y ya no hace falta: el acceso es la misma sesión de
// Google que usa el dashboard admin (RequireAuth.jsx ya redirige acá según
// session.user.role/botIds), así que esta página solo necesita `api.js`
// (fetch con credentials:'include', igual que DashboardPage) en vez de un
// mecanismo de auth propio.

function BotDashboard({ botId, onLogout }) {
  const [bot, setBot] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    const res = await api('GET', `/bots/${botId}`, null).catch(() => null)
    if (!res || res.detail) { setError(res?.detail || 'No se pudo cargar la bot'); return }
    setBot(res)
  }, [botId])

  useEffect(() => {
    load()
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [load])

  if (error) return <div className="empty" style={{ padding: 24 }}>{error}</div>
  if (!bot) return <div className="empty" style={{ padding: 24 }}>Cargando...</div>

  return (
    <div className="client-portal">
      <header>
        <span className="portal-title">🐙 {bot.name}</span>
        <div className="header-actions">
          <button className="btn-ghost btn-sm" onClick={onLogout}>Salir</button>
        </div>
      </header>
      <main className="portal-main" style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 16px' }}>
        <BotCard
          mode="bot"
          bot={normalizeBot(bot)}
          apiCall={api}
          onRefresh={load}
        />
      </main>
    </div>
  )
}

// Rol "scoped" con más de un bot (PRO): lista mínima de links, no un
// selector rico -- ver management/HANDOFF_VERCEL_DEEP_MIGRATION.md, la
// semilla honesta de PRO queda para un paso posterior.
function BotSelector({ botIds }) {
  return (
    <div className="connect-screen">
      <div className="connect-box">
        <div className="logo">🐙</div>
        <h1>Tus bots</h1>
        <p className="subtitle">Elegí a cuál entrar</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
          {botIds.map(id => (
            <a key={id} href={`/bot/${id}`} className="btn-ghost" style={{ textAlign: 'center' }}>{id}</a>
          ))}
        </div>
      </div>
    </div>
  )
}

function logout() {
  window.location.href = '/api/auth/signout?callbackUrl=/'
}

export default function BotPage() {
  const { botId } = useParams()
  const [botIds, setBotIds] = useState(null)

  useEffect(() => {
    if (botId) return
    fetch('/api/auth/session').then(r => r.json()).then(s => {
      setBotIds(s?.user?.botIds ?? [])
    }).catch(() => setBotIds([]))
  }, [botId])

  if (botId) {
    return <BotDashboard botId={botId} onLogout={logout} />
  }

  // Sin botId en la URL: RequireAuth ya nos manda acá solo cuando el
  // usuario tiene más de un bot (PRO) -- si por algún motivo tiene 0,
  // no hay nada útil que mostrar.
  if (botIds === null) return null
  return <BotSelector botIds={botIds} />
}
