import { useState, useEffect, useRef, useCallback } from 'react'
import { api, connectAndPoll } from '../api.js'
import ChatWidget from '../components/ChatWidget.jsx'

const STEPS = { pwd: 'pwd', phone: 'phone', portal: 'portal' }

// ─── Status badge ────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    ready:         { cls: 's-ready',        label: 'Conectado' },
    connecting:    { cls: 's-connecting',   label: 'Conectando' },
    qr_ready:      { cls: 's-qr_needed',    label: 'Sin iniciar' },
    qr_needed:     { cls: 's-qr_needed',    label: 'Sin iniciar' },
    authenticated: { cls: 's-authenticated',label: 'Autenticando' },
    disconnected:  { cls: 's-disconnected', label: 'Desconectado' },
    failed:        { cls: 's-failed',       label: 'Error' },
    stopped:       { cls: 's-disconnected', label: 'Sin iniciar' },
  }
  const { cls, label } = map[status] ?? { cls: 's-disconnected', label: status }
  return (
    <span className={`badge ${cls}`}>
      <span className="dot" />
      {label}
    </span>
  )
}

// ─── Chat con un contacto usando ChatWidget ──────────────────────
function ContactChat({ number, pwd, contact, onClose }) {
  const [messages, setMessages] = useState([])

  const load = useCallback(async () => {
    const res = await api('GET', `/client/${number}/chat/${contact.phone}`, null, pwd).catch(() => null)
    if (Array.isArray(res)) {
      setMessages(res.map(m => ({
        id: m.id,
        body: m.body,
        outbound: m.outbound,
        from: m.outbound ? null : (m.name || m.phone),
        time: m.timestamp?.slice(11, 16),
      })))
    }
  }, [number, pwd, contact.phone])

  useEffect(() => {
    load()
    const iv = setInterval(load, 4000)
    return () => clearInterval(iv)
  }, [load])

  async function handleSend(text) {
    const res = await api('POST', `/client/${number}/chat/${contact.phone}`, { text }, pwd).catch(() => null)
    if (res?.ok) load()
  }

  const unread = messages.filter(m => !m.outbound && !m.answered).length

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
        unreadCount={unread}
      />
    </div>
  )
}

// ─── Portal (dashboard del cliente) ─────────────────────────────
function ClientPortal({ number, pwd, onLogout }) {
  const [info, setInfo] = useState(null)
  const [conversations, setConversations] = useState([]) // últimos mensajes agrupados por contacto
  const [activeContact, setActiveContact] = useState(null)
  const [replyMsg, setReplyMsg] = useState('')
  const [savingMsg, setSavingMsg] = useState(false)
  const [saveResult, setSaveResult] = useState(null)

  // QR inline
  const [showQr, setShowQr] = useState(false)
  const [qrSrc, setQrSrc] = useState(null)
  const [qrStatus, setQrStatus] = useState('Generando código QR...')
  const stopQrRef = useRef(null)

  const loadInfo = useCallback(async () => {
    const res = await api('GET', `/client/${number}`, null, pwd).catch(() => null)
    if (!res || res.detail) return
    setInfo(res)
    setReplyMsg(prev => prev === '' ? (res.autoReplyMessage ?? '') : prev)
  }, [number, pwd])

  // Agrupa los últimos 30 mensajes por contacto → una fila por contacto
  const loadMessages = useCallback(async () => {
    const res = await api('GET', `/client/${number}/messages`, null, pwd).catch(() => null)
    if (!Array.isArray(res)) return
    // Deduplicar por phone, quedarse con el mensaje más reciente por contacto
    const seen = new Map()
    for (const m of res) {
      if (!seen.has(m.phone)) seen.set(m.phone, m)
    }
    setConversations([...seen.values()])
  }, [number, pwd])

  useEffect(() => {
    loadInfo()
    loadMessages()
    const interval = setInterval(() => { loadInfo(); loadMessages() }, 5000)
    return () => clearInterval(interval)
  }, [loadInfo, loadMessages])

  useEffect(() => () => stopQrRef.current?.(), [])

  async function handleConnect() {
    setShowQr(true)
    setQrSrc(null)
    setQrStatus('Generando código QR...')
    stopQrRef.current = await connectAndPoll({
      number, password: pwd,
      onQR(dataUrl) { setQrSrc(dataUrl); setQrStatus('El código se renueva cada 20 segundos') },
      onReady() { stopQrRef.current = null; setShowQr(false); loadInfo() },
      onError() { stopQrRef.current = null; setShowQr(false); loadInfo() },
    })
  }

  function handleCancelQr() { stopQrRef.current?.(); stopQrRef.current = null; setShowQr(false) }

  async function handleDisconnect() {
    await api('POST', `/client/${number}/disconnect`, null, pwd).catch(() => null)
    loadInfo()
  }

  async function handleSaveMessage() {
    setSavingMsg(true); setSaveResult(null)
    const res = await api('PUT', `/client/${number}`, { autoReplyMessage: replyMsg }, pwd).catch(() => null)
    setSavingMsg(false)
    setSaveResult(res?.ok ? 'ok' : 'error')
    if (res?.ok) loadInfo()
    setTimeout(() => setSaveResult(null), 3000)
  }

  const isConnected  = info?.status === 'ready'
  const isConnecting = ['connecting', 'qr_ready', 'authenticated'].includes(info?.status)
  const isTelegram   = info?.type === 'telegram'

  return (
    <div className="client-portal">
      <header>
        <span className="portal-title">{isTelegram ? '✈️' : '📱'} {info?.botName ?? number}</span>
        <div className="header-actions">
          <span className="portal-number">{isTelegram ? `TG ${number}` : `+${number}`}</span>
          <button className="btn-ghost btn-sm" onClick={onLogout}>Salir</button>
        </div>
      </header>

      <main className="portal-main">

        {/* ── Card 1: Estado ── */}
        <div className="card">
          <div className="card-title">Estado de conexión</div>
          <div className="portal-status-row">
            {info ? <StatusBadge status={info.status} /> : <StatusBadge status="stopped" />}
            <span className="portal-company">{info?.botName}</span>
          </div>
          {!isTelegram && !showQr && (
            <div className="portal-connect-actions">
              {isConnected && <button className="btn-danger btn-sm" onClick={handleDisconnect}>Desconectar</button>}
              {!isConnected && !isConnecting && <button className="btn-primary btn-sm" onClick={handleConnect}>Conectar</button>}
              {isConnecting && !showQr && <span className="portal-connecting-hint">Conectando...</span>}
            </div>
          )}
          {!isTelegram && showQr && (
            <div className="portal-qr-section">
              <p className="qr-hint">Abrí WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong></p>
              <div className="qr-wrap">{qrSrc ? <img src={qrSrc} alt="QR" /> : <div className="spinner" />}</div>
              <p className="qr-status">{qrStatus}</p>
              <button className="btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={handleCancelQr}>Cancelar</button>
            </div>
          )}
        </div>

        {/* ── Card 2: Mensaje automático ── */}
        <div className="card">
          <div className="card-title">Mensaje de respuesta automática</div>
          {info && !info.hasOwnMessage && (
            <p className="portal-inherited-hint">Heredado de la empresa. Podés personalizar este mensaje.</p>
          )}
          <div className="fg">
            <textarea rows={8} value={replyMsg} onChange={e => setReplyMsg(e.target.value)}
              placeholder="Ej: Hola, te responderemos a la brevedad." />
          </div>
          <div className="portal-save-row">
            <button className="btn-primary btn-sm" onClick={handleSaveMessage} disabled={savingMsg}>
              {savingMsg ? 'Guardando...' : 'Guardar'}
            </button>
            {saveResult === 'ok'    && <span className="portal-save-ok">✓ Guardado</span>}
            {saveResult === 'error' && <span className="portal-save-err">Error al guardar</span>}
          </div>
        </div>

        {/* ── Card 3: Conversaciones / Chat ── */}
        <div className="card">
          <div className="section-header">
            <h2>Conversaciones</h2>
            <span className="portal-refresh-hint">Actualiza cada 5 seg.</span>
          </div>

          {activeContact && (
            <ContactChat
              number={number}
              pwd={pwd}
              contact={activeContact}
              onClose={() => { setActiveContact(null); loadMessages() }}
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
                      onClick={() => setActiveContact({ phone: m.phone, name: m.name })}
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

      </main>
    </div>
  )
}

// ─── Página principal ────────────────────────────────────────────
export default function ConnectPage() {
  const [step, setStep] = useState(STEPS.pwd)
  const [pwd, setPwd] = useState('')
  const [pwdError, setPwdError] = useState('')
  const [phone, setPhone] = useState('')
  const [phoneError, setPhoneError] = useState('')

  useEffect(() => {
    const savedPwd = sessionStorage.getItem('client_pwd')
    const savedPhone = sessionStorage.getItem('client_phone')
    if (!savedPwd) return
    api('POST', '/auth', { password: savedPwd })
      .then(res => {
        if (res.ok) {
          setPwd(savedPwd)
          if (savedPhone) { setPhone(savedPhone); setStep(STEPS.portal) }
          else setStep(STEPS.phone)
        } else {
          sessionStorage.removeItem('client_pwd')
          sessionStorage.removeItem('client_phone')
        }
      }).catch(() => {})
  }, [])

  async function doLogin(e) {
    e.preventDefault(); setPwdError('')
    const res = await api('POST', '/auth', { password: pwd }).catch(() => null)
    if (!res?.ok) { setPwdError('Clave incorrecta. Verificá con el administrador.'); return }
    sessionStorage.setItem('client_pwd', pwd)
    setStep(STEPS.phone)
  }

  async function doEnterPortal(e) {
    e.preventDefault()
    const input = phone.trim()
    if (!input) { setPhoneError('Ingresá tu número de teléfono.'); return }
    const res = await api('GET', `/client/${input}`, null, pwd).catch(() => null)
    if (!res || res.detail) { setPhoneError('Número no encontrado. Verificá con el administrador.'); return }
    setPhoneError('')
    // Usar el número canónico que devuelve la API (normaliza tokenId corto → session_id completo)
    const canonical = res.number
    setPhone(canonical)
    sessionStorage.setItem('client_phone', canonical)
    setStep(STEPS.portal)
  }

  function handleLogout() {
    sessionStorage.removeItem('client_pwd')
    sessionStorage.removeItem('client_phone')
    setPwd(''); setPhone(''); setStep(STEPS.pwd)
  }

  if (step === STEPS.portal) return <ClientPortal number={phone} pwd={pwd} onLogout={handleLogout} />

  return (
    <div className="connect-screen">
      <div className="connect-box">
        <div className="logo">📱</div>
        {step === STEPS.pwd && (
          <>
            <h1>Conectar WhatsApp</h1>
            <p className="subtitle">Ingresá la clave de acceso que te proporcionó el administrador</p>
            <div className="error">{pwdError}</div>
            <form onSubmit={doLogin}>
              <input type="password" placeholder="Clave de acceso" value={pwd}
                onChange={e => setPwd(e.target.value)} autoFocus />
              <button type="submit" className="btn-connect">Continuar</button>
            </form>
          </>
        )}
        {step === STEPS.phone && (
          <>
            <h1>Acceder al portal</h1>
            <p className="subtitle">Ingresá tu número de WhatsApp o el ID de tu bot de Telegram</p>
            <div className="error">{phoneError}</div>
            <form onSubmit={doEnterPortal}>
              <input type="text" placeholder="5491155612767 o bot_test-tg-8672986634" value={phone}
                onChange={e => setPhone(e.target.value)} autoFocus />
              <button type="submit" className="btn-connect">Ir al portal</button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
