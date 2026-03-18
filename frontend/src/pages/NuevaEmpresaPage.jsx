import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import StatusBadge from '../components/StatusBadge.jsx'

function empresaApi(method, path, body, pwd) {
  const headers = { 'Content-Type': 'application/json' }
  if (pwd) headers['x-empresa-pwd'] = pwd
  return fetch('/api' + path, { method, headers, body: body ? JSON.stringify(body) : undefined })
    .then(r => r.json())
}

// ─── Fila de conexión (igual que DashboardPage pero con empresa auth) ─────────

export function ConexionRow({ conn, botId, pwd, onDelete, onConnected }) {
  const [showQr, setShowQr]     = useState(false)
  const [qrSrc, setQrSrc]       = useState(null)
  const [qrStatus, setQrStatus] = useState('')
  const [status, setStatus]     = useState(conn.status)
  const stopRef = useRef(null)

  useEffect(() => setStatus(conn.status), [conn.status])
  useEffect(() => () => stopRef.current?.(), [])

  const isTelegram  = conn.type === 'telegram'
  const isConnected = status === 'ready'
  const isConnecting = ['connecting', 'qr_needed', 'qr_ready', 'authenticated'].includes(status)

  async function handleConnect() {
    setShowQr(true); setQrSrc(null); setQrStatus('Iniciando...')
    let interval = null
    const stop = () => { if (interval) { clearInterval(interval); interval = null } }
    stopRef.current = stop

    const res = await empresaApi('POST', `/empresa/${botId}/connect/${conn.id}`, null, pwd).catch(() => null)
    if (!res) { stop(); setShowQr(false); return }
    if (res.status === 'ready') { stop(); setStatus('ready'); setShowQr(false); onConnected?.(); return }

    interval = setInterval(async () => {
      const data = await empresaApi('GET', `/empresa/${botId}/qr/${conn.id}`, null, pwd).catch(() => null)
      if (!data) return
      if (data.status === 'ready') { stop(); setStatus('ready'); setShowQr(false); onConnected?.() }
      else if (['failed', 'disconnected'].includes(data.status)) { stop(); setStatus(data.status); setShowQr(false) }
      else {
        setStatus(data.status)
        if (data.qr) { setQrSrc(data.qr); setQrStatus('El código se renueva cada 20 segundos') }
      }
    }, 3000)
  }

  async function handleDisconnect() {
    await empresaApi('POST', `/empresa/${botId}/disconnect/${conn.id}`, null, pwd).catch(() => null)
    setStatus('disconnected')
  }

  return (
    <div>
      <div className="phone-row" style={{ background: isTelegram ? '#f0f4ff' : undefined }}>
        <div className="phone-number">
          <span className={isTelegram ? 'tg-label' : 'wa-label'}>{isTelegram ? 'TG' : 'WA'}</span>
          <span className="phone-id">{isTelegram ? conn.id : `+${conn.id}`}</span>
        </div>
        <div style={{ flex: 1 }} />
        <div className="phone-actions">
          <StatusBadge status={status} />
          {!isTelegram && !showQr && !isConnected && !isConnecting && (
            <button className="btn-primary btn-sm" onClick={handleConnect}>Vincular QR</button>
          )}
          {!isTelegram && !showQr && isConnected && (
            <button className="btn-danger btn-sm" onClick={handleDisconnect}>Desconectar</button>
          )}
          {!isTelegram && isConnecting && !showQr && (
            <span style={{ fontSize: 12, color: '#888' }}>Conectando...</span>
          )}
          <button className="btn-danger btn-sm" onClick={() => onDelete(conn)}>Eliminar</button>
        </div>
      </div>

      {showQr && (
        <div className="portal-qr-section" style={{ marginLeft: 16, marginBottom: 8 }}>
          <p className="qr-hint">
            Abrí WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong>
          </p>
          <div className="qr-wrap">{qrSrc ? <img src={qrSrc} alt="QR" /> : <div className="spinner" />}</div>
          <p className="qr-status">{qrStatus}</p>
          <button className="btn-ghost btn-sm" style={{ marginTop: 8 }}
            onClick={() => { stopRef.current?.(); setShowQr(false) }}>Cancelar</button>
        </div>
      )}
    </div>
  )
}

// ─── Paso 1: Datos de la empresa ─────────────────────────────────

function StepDatos({ onCreated }) {
  const [form, setForm] = useState({ name: '', password: '', confirm: '', autoReplyMessage: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault(); setError('')
    if (!form.name.trim()) { setError('El nombre es requerido'); return }
    if (!form.password) { setError('La contraseña es requerida'); return }
    if (form.password !== form.confirm) { setError('Las contraseñas no coinciden'); return }

    setLoading(true)
    const res = await fetch('/api/empresa/nueva', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: form.name, password: form.password, autoReplyMessage: form.autoReplyMessage }),
    }).then(r => r.json()).catch(() => null)
    setLoading(false)

    if (!res?.ok) { setError(res?.detail || 'Error al crear la empresa'); return }
    onCreated({ botId: res.bot_id, botName: res.bot_name, pwd: form.password })
  }

  return (
    <div className="connect-box" style={{ maxWidth: 480, width: '100%' }}>
      <div className="logo">🐙</div>
      <h1>Nueva empresa</h1>
      <p className="subtitle">Configurá los datos de tu empresa para empezar</p>
      {error && <div className="error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="fg">
          <label>Nombre de la empresa</label>
          <input value={form.name} onChange={set('name')} placeholder="Herrería García" autoFocus />
        </div>
        <div className="fg">
          <label>Contraseña de acceso</label>
          <input type="password" value={form.password} onChange={set('password')} placeholder="Elegí una clave segura" />
        </div>
        <div className="fg">
          <label>Confirmar contraseña</label>
          <input type="password" value={form.confirm} onChange={set('confirm')} placeholder="Repetí la clave" />
        </div>
        <div className="fg">
          <label>Mensaje de respuesta automática</label>
          <textarea rows={4} value={form.autoReplyMessage} onChange={set('autoReplyMessage')}
            placeholder="Ej: Hola, te responderemos a la brevedad." />
        </div>
        <button type="submit" className="btn-connect" disabled={loading}>
          {loading ? 'Creando...' : 'Continuar →'}
        </button>
      </form>
    </div>
  )
}

// ─── Paso 2: Agregar conexiones ───────────────────────────────────

function StepConexiones({ session, onDone }) {
  const { botId, pwd } = session
  const [conns, setConns]       = useState([])
  const [waInput, setWaInput]   = useState('')
  const [tgInput, setTgInput]   = useState('')
  const [waError, setWaError]   = useState('')
  const [tgError, setTgError]   = useState('')
  const [loading, setLoading]   = useState(false)

  async function addWa(e) {
    e.preventDefault(); setWaError('')
    const number = waInput.trim()
    if (!number) return
    setLoading(true)
    const res = await empresaApi('POST', `/empresa/${botId}/whatsapp`, { number }, pwd).catch(() => null)
    setLoading(false)
    if (!res?.ok) { setWaError(res?.detail || 'Error al agregar'); return }
    setConns(c => [...c, { id: number, type: 'whatsapp', status: 'stopped' }])
    setWaInput('')
  }

  async function addTg(e) {
    e.preventDefault(); setTgError('')
    const token = tgInput.trim()
    if (!token) return
    setLoading(true)
    const res = await empresaApi('POST', `/empresa/${botId}/telegram`, { token }, pwd).catch(() => null)
    setLoading(false)
    if (!res?.ok) { setTgError(res?.detail || 'Error al agregar'); return }
    const tokenId = token.split(':')[0]
    const sessionId = `${botId}-tg-${tokenId}`
    setConns(c => [...c, { id: sessionId, type: 'telegram', status: res.requires_restart ? 'stopped' : 'ready' }])
    if (res.requires_restart) setTgError('Bot agregado. Requiere reinicio del servidor para activarse.')
    else setTgError('')
    setTgInput('')
  }

  async function removeConn(conn) {
    if (conn.type === 'whatsapp') {
      await empresaApi('DELETE', `/empresa/${botId}/whatsapp/${conn.id}`, null, pwd).catch(() => null)
    } else {
      const tokenId = conn.id.split('-tg-')[1]
      await empresaApi('DELETE', `/empresa/${botId}/telegram/${tokenId}`, null, pwd).catch(() => null)
    }
    setConns(c => c.filter(x => x.id !== conn.id))
  }

  return (
    <div style={{ maxWidth: 580, width: '100%' }}>
      <div className="logo">🔌</div>
      <h1>Agregar conexiones</h1>
      <p className="subtitle">Conectá tus canales de WhatsApp y Telegram. Podés hacerlo ahora o más tarde.</p>

      {/* WhatsApp */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">📱 WhatsApp</div>
        <form onSubmit={addWa} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input style={{ flex: 1 }} type="tel" value={waInput} onChange={e => setWaInput(e.target.value)}
            placeholder="Número sin + (ej: 5491155612767)" />
          <button type="submit" className="btn-primary btn-sm" disabled={loading}>Agregar</button>
        </form>
        {waError && <div className="error" style={{ marginBottom: 8 }}>{waError}</div>}
        <div className="phones-table">
          {conns.filter(c => c.type === 'whatsapp').map(c => (
            <ConexionRow key={c.id} conn={c} botId={botId} pwd={pwd}
              onDelete={removeConn} onConnected={() => setConns(cs => cs.map(x => x.id === c.id ? { ...x, status: 'ready' } : x))} />
          ))}
          {conns.filter(c => c.type === 'whatsapp').length === 0 && (
            <div className="empty" style={{ padding: 8 }}>Sin números aún</div>
          )}
        </div>
      </div>

      {/* Telegram */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-title">✈️ Telegram</div>
        <form onSubmit={addTg} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input style={{ flex: 1 }} value={tgInput} onChange={e => setTgInput(e.target.value)}
            placeholder="Token de @BotFather (123456:ABC...)" />
          <button type="submit" className="btn-primary btn-sm" disabled={loading}>Agregar</button>
        </form>
        {tgError && <div style={{ fontSize: 13, color: tgError.includes('Requiere') ? '#b45309' : 'var(--error)', marginBottom: 8 }}>{tgError}</div>}
        <div className="phones-table">
          {conns.filter(c => c.type === 'telegram').map(c => (
            <ConexionRow key={c.id} conn={c} botId={botId} pwd={pwd} onDelete={removeConn} />
          ))}
          {conns.filter(c => c.type === 'telegram').length === 0 && (
            <div className="empty" style={{ padding: 8 }}>Sin bots aún</div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
        <button className="btn-ghost" onClick={onDone}>Omitir por ahora</button>
        <button className="btn-primary" onClick={onDone} disabled={conns.length === 0}>
          Listo →
        </button>
      </div>
    </div>
  )
}

// ─── Paso 3: Todo listo ───────────────────────────────────────────

function StepListo({ session }) {
  const navigate = useNavigate()

  function goPortal() {
    sessionStorage.setItem('empresa_bot_id', session.botId)
    sessionStorage.setItem('empresa_pwd', session.pwd)
    navigate('/empresa')
  }

  return (
    <div className="connect-box" style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 64, marginBottom: 16 }}>🎉</div>
      <h1>¡Todo listo!</h1>
      <p className="subtitle">
        <strong>{session.botName}</strong> está configurada y lista para usar.
      </p>
      <p className="subtitle" style={{ marginTop: 8, fontSize: 13, color: '#888' }}>
        Guardá tu contraseña: podés entrar en cualquier momento desde el portal de empresa.
      </p>
      <button className="btn-connect" style={{ marginTop: 24 }} onClick={goPortal}>
        Ir a mi portal →
      </button>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────

export default function NuevaEmpresaPage() {
  const [step, setStep]       = useState('datos')
  const [session, setSession] = useState(null)

  function handleCreated(sess) {
    sessionStorage.setItem('empresa_bot_id', sess.botId)
    sessionStorage.setItem('empresa_pwd', sess.pwd)
    setSession(sess)
    setStep('conexiones')
  }

  return (
    <div className="connect-screen" style={{ alignItems: 'flex-start', paddingTop: 40 }}>
      {step === 'datos'      && <StepDatos onCreated={handleCreated} />}
      {step === 'conexiones' && <StepConexiones session={session} onDone={() => setStep('listo')} />}
      {step === 'listo'      && <StepListo session={session} />}
    </div>
  )
}
