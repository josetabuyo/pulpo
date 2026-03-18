import { useState, useEffect, useRef, useCallback } from 'react'
import StatusBadge from '../components/StatusBadge.jsx'
import ChatWidget from '../components/ChatWidget.jsx'

// ─── Helpers de API empresa ──────────────────────────────────────

function empresaApi(method, path, body, pwd) {
  const headers = { 'Content-Type': 'application/json', 'x-empresa-pwd': pwd }
  return fetch('/api' + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json())
}

async function connectAndPollEmpresa({ botId, number, pwd, onQR, onReady, onError }) {
  let interval = null
  const stop = () => { if (interval) { clearInterval(interval); interval = null } }

  let res
  try {
    res = await empresaApi('POST', `/empresa/${botId}/connect/${number}`, null, pwd)
  } catch {
    onError('Error de red.')
    return stop
  }

  if (res.error) { onError(res.error); return stop }
  if (res.status === 'ready') { onReady(); return stop }

  const sessionId = res.sessionId

  interval = setInterval(async () => {
    try {
      const data = await empresaApi('GET', `/empresa/${botId}/qr/${sessionId}`, null, pwd)
      if (data.status === 'ready') { stop(); onReady(); return }
      if (data.status === 'failed' || data.status === 'disconnected') {
        stop(); onError('Error al conectar. Intentá de nuevo.'); return
      }
      if (data.qr) onQR(data.qr)
    } catch {}
  }, 3000)

  return stop
}

// ─── Chat con un contacto ────────────────────────────────────────

function ContactChat({ botId, number, pwd, contact, onClose }) {
  const [messages, setMessages] = useState([])

  const load = useCallback(async () => {
    const res = await empresaApi('GET', `/empresa/${botId}/chat/${number}/${contact.phone}`, null, pwd).catch(() => null)
    if (Array.isArray(res)) {
      setMessages(res.map(m => ({
        id: m.id,
        body: m.body,
        outbound: m.outbound,
        from: m.outbound ? null : (m.name || m.phone),
        time: m.timestamp?.slice(11, 16),
      })))
    }
  }, [botId, number, pwd, contact.phone])

  useEffect(() => {
    load()
    const iv = setInterval(load, 4000)
    return () => clearInterval(iv)
  }, [load])

  async function handleSend(text) {
    const res = await empresaApi('POST', `/empresa/${botId}/chat/${number}/${contact.phone}`, { text }, pwd).catch(() => null)
    if (res?.ok) load()
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
        <button className="btn-ghost btn-sm" onClick={onClose}>✕ Cerrar chat</button>
      </div>
      <ChatWidget
        title={contact.name || contact.phone}
        subtitle={contact.phone}
        messages={messages}
        onSend={handleSend}
        defaultOpen={true}
        unreadCount={0}
      />
    </div>
  )
}

// ─── ConexionCard ────────────────────────────────────────────────

function ConexionCard({ conn, botId, pwd, onRefresh }) {
  const [showQr, setShowQr]         = useState(false)
  const [qrSrc, setQrSrc]           = useState(null)
  const [qrStatus, setQrStatus]     = useState('')
  const [conversations, setConvs]   = useState([])
  const [activeContact, setContact] = useState(null)
  const stopRef = useRef(null)

  const isConnected  = conn.status === 'ready'
  const isConnecting = ['connecting', 'qr_needed', 'qr_ready', 'authenticated'].includes(conn.status)
  const isTelegram   = conn.type === 'telegram'

  const loadConvs = useCallback(async () => {
    if (isTelegram) return
    const res = await empresaApi('GET', `/empresa/${botId}/messages/${conn.id}`, null, pwd).catch(() => null)
    if (Array.isArray(res)) setConvs(res)
  }, [botId, conn.id, pwd, isTelegram])

  useEffect(() => {
    loadConvs()
    const iv = setInterval(loadConvs, 5000)
    return () => { clearInterval(iv); stopRef.current?.() }
  }, [loadConvs])

  async function handleConnect() {
    setShowQr(true); setQrSrc(null); setQrStatus('Generando código QR...')
    stopRef.current = await connectAndPollEmpresa({
      botId, number: conn.id, pwd,
      onQR(dataUrl) { setQrSrc(dataUrl); setQrStatus('El código se renueva cada 20 segundos') },
      onReady() { stopRef.current = null; setShowQr(false); onRefresh() },
      onError() { stopRef.current = null; setShowQr(false); onRefresh() },
    })
  }

  function handleCancelQr() { stopRef.current?.(); stopRef.current = null; setShowQr(false) }

  async function handleDisconnect() {
    await empresaApi('POST', `/empresa/${botId}/disconnect/${conn.id}`, null, pwd).catch(() => null)
    onRefresh()
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>

      {/* Header de la conexión */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 20 }}>{isTelegram ? '✈️' : '📱'}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>
            {isTelegram ? conn.number : `+${conn.number}`}
          </div>
        </div>
        <StatusBadge status={conn.status} />
      </div>

      {/* Acciones WA */}
      {!isTelegram && !showQr && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {isConnected && (
            <button className="btn-danger btn-sm" onClick={handleDisconnect}>Desconectar</button>
          )}
          {!isConnected && !isConnecting && (
            <button className="btn-primary btn-sm" onClick={handleConnect}>Conectar</button>
          )}
          {isConnecting && <span className="portal-connecting-hint">Conectando...</span>}
        </div>
      )}

      {/* QR */}
      {!isTelegram && showQr && (
        <div className="portal-qr-section" style={{ marginBottom: 12 }}>
          <p className="qr-hint">Abrí WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong></p>
          <div className="qr-wrap">{qrSrc ? <img src={qrSrc} alt="QR" /> : <div className="spinner" />}</div>
          <p className="qr-status">{qrStatus}</p>
          <button className="btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={handleCancelQr}>Cancelar</button>
        </div>
      )}

      {/* Conversaciones WA */}
      {!isTelegram && (
        <div>
          <div className="section-header" style={{ marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted, #888)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Conversaciones
            </span>
            <span className="portal-refresh-hint">Actualiza cada 5 seg.</span>
          </div>

          {activeContact && (
            <ContactChat
              botId={botId}
              number={conn.id}
              pwd={pwd}
              contact={activeContact}
              onClose={() => { setContact(null); loadConvs() }}
            />
          )}

          {!activeContact && (
            conversations.length === 0
              ? <div className="empty">Sin mensajes aún</div>
              : (
                <div className="portal-conversations">
                  {conversations.map(m => (
                    <button
                      key={m.phone}
                      className="conv-row"
                      onClick={() => setContact({ phone: m.phone, name: m.name })}
                    >
                      <div className="conv-avatar">{(m.name || m.phone).slice(0, 2).toUpperCase()}</div>
                      <div className="conv-info">
                        <div className="conv-name">{m.name || m.phone}</div>
                        <div className="conv-preview">{m.body}</div>
                      </div>
                      <div className="conv-meta">
                        <div className="conv-time">{m.timestamp?.slice(11, 16)}</div>
                        {!m.answered && <span className="conv-unread" />}
                      </div>
                    </button>
                  ))}
                </div>
              )
          )}
        </div>
      )}

    </div>
  )
}

// ─── EmpresaDashboard ────────────────────────────────────────────

function EmpresaDashboard({ botId, botName, pwd, onLogout }) {
  const [data, setData]             = useState(null)
  const [replyMsg, setReplyMsg]     = useState('')
  const [saving, setSaving]         = useState(false)
  const [saveResult, setSaveResult] = useState(null)

  const load = useCallback(async () => {
    const res = await empresaApi('GET', `/empresa/${botId}`, null, pwd).catch(() => null)
    if (!res || res.detail) return
    setData(res)
    setReplyMsg(prev => prev === '' ? (res.autoReplyMessage ?? '') : prev)
  }, [botId, pwd])

  useEffect(() => {
    load()
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [load])

  async function handleSaveTools() {
    setSaving(true); setSaveResult(null)
    const res = await empresaApi('PUT', `/empresa/${botId}/tools`, { autoReplyMessage: replyMsg }, pwd).catch(() => null)
    setSaving(false)
    setSaveResult(res?.ok ? 'ok' : 'error')
    if (res?.ok) load()
    setTimeout(() => setSaveResult(null), 3000)
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

        {/* Conexiones (estado + acciones + conversaciones) */}
        <div className="card">
          <div className="card-title">Conexiones</div>
          {data?.connections?.length === 0 && (
            <div className="empty">Sin conexiones configuradas.</div>
          )}
          {data?.connections?.map(conn => (
            <ConexionCard
              key={conn.id}
              conn={conn}
              botId={botId}
              pwd={pwd}
              onRefresh={load}
            />
          ))}
        </div>

        {/* Auto-reply a nivel empresa */}
        <div className="card">
          <div className="card-title">Mensaje de respuesta automática</div>
          <div className="fg">
            <textarea
              rows={6}
              value={replyMsg}
              onChange={e => setReplyMsg(e.target.value)}
              placeholder="Ej: Hola, te responderemos a la brevedad."
            />
          </div>
          <div className="portal-save-row">
            <button className="btn-primary btn-sm" onClick={handleSaveTools} disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
            {saveResult === 'ok'    && <span className="portal-save-ok">✓ Guardado</span>}
            {saveResult === 'error' && <span className="portal-save-err">Error al guardar</span>}
          </div>
        </div>

      </main>
    </div>
  )
}

// ─── EmpresaLogin ────────────────────────────────────────────────

function EmpresaLogin({ onLogin }) {
  const [pwd, setPwd]     = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault(); setError('')
    const res = await fetch('/api/empresa/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd }),
    }).then(r => r.json()).catch(() => null)

    if (!res?.ok) { setError('Contraseña incorrecta.'); return }
    sessionStorage.setItem('empresa_bot_id', res.bot_id)
    sessionStorage.setItem('empresa_pwd', pwd)
    onLogin({ botId: res.bot_id, botName: res.bot_name, pwd })
  }

  return (
    <div className="connect-screen">
      <div className="connect-box">
        <div className="logo">🐙</div>
        <h1>Portal de empresa</h1>
        <p className="subtitle">Ingresá la clave de tu empresa</p>
        <div className="error">{error}</div>
        <form onSubmit={handleSubmit}>
          <input type="password" placeholder="Clave de acceso" value={pwd}
            onChange={e => setPwd(e.target.value)} autoFocus />
          <button type="submit" className="btn-connect">Entrar</button>
        </form>
      </div>
    </div>
  )
}

// ─── Página principal ────────────────────────────────────────────

export default function EmpresaPage() {
  const [session, setSession] = useState(null)

  useEffect(() => {
    const botId = sessionStorage.getItem('empresa_bot_id')
    const pwd   = sessionStorage.getItem('empresa_pwd')
    if (!botId || !pwd) return

    fetch('/api/empresa/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd }),
    }).then(r => r.json()).then(res => {
      if (res.ok) setSession({ botId: res.bot_id, botName: res.bot_name, pwd })
      else {
        sessionStorage.removeItem('empresa_bot_id')
        sessionStorage.removeItem('empresa_pwd')
      }
    }).catch(() => {})
  }, [])

  function handleLogin({ botId, botName, pwd }) {
    setSession({ botId, botName, pwd })
  }

  function handleLogout() {
    sessionStorage.removeItem('empresa_bot_id')
    sessionStorage.removeItem('empresa_pwd')
    setSession(null)
  }

  if (session) {
    return (
      <EmpresaDashboard
        botId={session.botId}
        botName={session.botName}
        pwd={session.pwd}
        onLogout={handleLogout}
      />
    )
  }

  return <EmpresaLogin onLogin={handleLogin} />
}
