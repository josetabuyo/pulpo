import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { authFetch, setAccessToken, clearAccessToken, getAccessToken } from '../lib/auth.js'
import EmpresaCard from '../components/EmpresaCard.jsx'

// ─── Helpers de API empresa ──────────────────────────────────────

async function empresaApi(method, path, body) {
  const res = await authFetch('/api' + path, {
    method,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) return { _unauthorized: true }
  return res.json()
}

// ─── EmpresaDashboard ────────────────────────────────────────────

function EmpresaDashboard({ botId, botName: initialBotName, onLogout }) {
  const [botName, setBotName] = useState(initialBotName)
  const [data, setData]       = useState(null)

  const load = useCallback(async () => {
    const res = await empresaApi('GET', `/empresa/${botId}`, null).catch(() => null)
    if (!res || res.detail) return
    setData(res)
    setBotName(res.bot_name)
  }, [botId])

  useEffect(() => {
    load()
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [load])

  const bot = {
    id: botId,
    name: botName,
    connections: (data?.connections ?? []).map(conn => ({
      id: conn.id,
      type: conn.type,
      number: conn.type === 'telegram' ? conn.id.split('-tg-').pop() : conn.id,
      status: conn.status,
    })),
  }

  return (
    <div className="client-portal">
      <header>
        <span className="portal-title">🐙 {botName}</span>
        <div className="header-actions">
          <button className="btn-ghost btn-sm" onClick={onLogout}>Salir</button>
        </div>
      </header>
      <main className="portal-main">
        <EmpresaCard
          mode="empresa"
          bot={bot}
          apiCall={empresaApi}
          onRefresh={load}
        />
      </main>
    </div>
  )
}

// ─── EmpresaLogin ────────────────────────────────────────────────

function EmpresaLogin({ onLogin }) {
  const [botId, setBotId] = useState('')
  const [pwd, setPwd]     = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault(); setError('')
    const res = await fetch('/api/empresa/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ bot_id: botId.trim(), password: pwd }),
    }).then(r => r.json()).catch(() => null)

    if (!res?.access_token) { setError('Credenciales incorrectas.'); return }

    setAccessToken(res.access_token)
    localStorage.setItem('empresa_bot_id', res.bot_id)

    // Obtener nombre de la empresa
    const me = await fetch('/api/empresa/me', {
      headers: { 'Authorization': `Bearer ${res.access_token}` },
    }).then(r => r.json()).catch(() => null)

    onLogin({ botId: res.bot_id, botName: me?.nombre ?? res.bot_id })
  }

  return (
    <div className="connect-screen">
      <div className="connect-box">
        <div className="logo">🐙</div>
        <h1>Portal de empresa</h1>
        <p className="subtitle">Ingresá tus credenciales</p>
        <div className="error">{error}</div>
        <form onSubmit={handleSubmit}>
          <input placeholder="ID de empresa (ej: bot_test)" value={botId}
            onChange={e => setBotId(e.target.value)} autoFocus />
          <input type="password" placeholder="Contraseña" value={pwd}
            onChange={e => setPwd(e.target.value)} />
          <button type="submit" className="btn-connect">Entrar</button>
        </form>
        <div className="connect-divider">¿Primera vez?</div>
        <Link to="/empresa/nueva" className="btn-ghost btn-sm" style={{ textAlign: 'center', display: 'block' }}>
          Crear empresa nueva →
        </Link>
      </div>
    </div>
  )
}

// ─── Página principal ────────────────────────────────────────────

export default function EmpresaPage() {
  const [session, setSession] = useState(null)

  useEffect(() => {
    const token = getAccessToken()
    const botId = localStorage.getItem('empresa_bot_id')
    if (!token || !botId) return

    // Verificar que el token sigue siendo válido
    fetch('/api/empresa/me', {
      headers: { 'Authorization': `Bearer ${token}` },
      credentials: 'include',
    }).then(r => {
      if (r.ok) return r.json()
      // Intentar refresh
      return fetch('/api/empresa/refresh', { method: 'POST', credentials: 'include' })
        .then(r2 => {
          if (!r2.ok) throw new Error('refresh failed')
          return r2.json()
        })
        .then(data => {
          setAccessToken(data.access_token)
          return fetch('/api/empresa/me', {
            headers: { 'Authorization': `Bearer ${data.access_token}` },
          }).then(r3 => r3.ok ? r3.json() : null)
        })
    }).then(me => {
      if (me?.bot_id) setSession({ botId: me.bot_id, botName: me.nombre })
      else {
        clearAccessToken()
        localStorage.removeItem('empresa_bot_id')
      }
    }).catch(() => {
      clearAccessToken()
      localStorage.removeItem('empresa_bot_id')
    })
  }, [])

  function handleLogin({ botId, botName }) {
    setSession({ botId, botName })
  }

  async function handleLogout() {
    await fetch('/api/empresa/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
    clearAccessToken()
    localStorage.removeItem('empresa_bot_id')
    setSession(null)
  }

  if (session) {
    return (
      <EmpresaDashboard
        botId={session.botId}
        botName={session.botName}
        onLogout={handleLogout}
      />
    )
  }

  return <EmpresaLogin onLogin={handleLogin} />
}
