import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, connectAndPoll } from '../api.js'
import SimChat from '../SimChat.jsx'

const STATUS_LABELS = {
  ready: 'Conectado', qr_ready: 'Esperando escaneo',
  connecting: 'Conectando', authenticated: 'Autenticando',
  disconnected: 'Desconectado', failed: 'Error', stopped: 'Sin iniciar',
  qr_needed: 'Sin iniciar',
}

// ─── Modales inline ────────────────────────────────────────────────────────────

function Modal({ open, onClose, title, width, children }) {
  useEffect(() => {
    if (!open) return
    const handler = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  return (
    <div className={`overlay${open ? ' open' : ''}`} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={width ? { width } : {}}>
        <button className="modal-close" onClick={onClose}>✕</button>
        {children}
      </div>
    </div>
  )
}

function BotModal({ open, onClose, editBot, onSave }) {
  const isEdit = !!editBot
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (open) {
      setId(editBot?.id ?? '')
      setName(editBot?.name ?? '')
      setMessage(editBot?.autoReplyMessage ?? '')
    }
  }, [open, editBot])

  function handleSave() {
    if (!name.trim() || !message.trim()) return alert('Nombre y mensaje son requeridos.')
    if (!isEdit && !id.trim()) return alert('ID es requerido.')
    onSave({ id: id.trim(), name: name.trim(), autoReplyMessage: message.trim() })
  }

  return (
    <Modal open={open} onClose={onClose} title="">
      <h3>{isEdit ? 'Editar empresa' : 'Nueva empresa'}</h3>
      {!isEdit && (
        <div className="fg">
          <label>ID (sin espacios, ej: bot_guardia)</label>
          <input value={id} onChange={e => setId(e.target.value)} placeholder="bot_guardia" />
        </div>
      )}
      <div className="fg">
        <label>Nombre de la empresa</label>
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Herrería García" />
      </div>
      <div className="fg">
        <label>Mensaje de respuesta automática</label>
        <textarea value={message} onChange={e => setMessage(e.target.value)} placeholder="Hola! Estamos fuera de horario..." />
      </div>
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" onClick={handleSave}>Guardar</button>
      </div>
    </Modal>
  )
}

function PhoneModal({ open, onClose, editPhone, botId, allBots, onSave }) {
  const isEdit = !!editPhone
  const [number, setNumber] = useState('')
  const [contacts, setContacts] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (open) {
      setNumber(editPhone?.number ?? '')
      setContacts(editPhone?.allowedContacts?.join(', ') ?? '')
      setMessage(editPhone?.autoReplyMessage ?? '')
    }
  }, [open, editPhone])

  function handleSave() {
    if (!isEdit && !number.trim()) return alert('Número requerido.')
    const allowedContacts = contacts.split(',').map(c => c.trim()).filter(Boolean)
    onSave({ number: number.trim(), allowedContacts, autoReplyMessage: message.trim(), botId })
  }

  return (
    <Modal open={open} onClose={onClose}>
      <h3>{isEdit ? 'Editar teléfono' : 'Agregar teléfono'}</h3>
      {!isEdit && (
        <div className="fg">
          <label>Número (sin +)</label>
          <input type="tel" value={number} onChange={e => setNumber(e.target.value)} placeholder="5491155612767" />
        </div>
      )}
      <div className="fg">
        <label>Contactos permitidos (separados por coma)</label>
        <input value={contacts} onChange={e => setContacts(e.target.value)} placeholder="Juan García, María López" />
      </div>
      <div className="fg">
        <label>Mensaje personalizado (opcional)</label>
        <textarea value={message} onChange={e => setMessage(e.target.value)} placeholder="Dejar vacío para usar el de la empresa" />
      </div>
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" onClick={handleSave}>Guardar</button>
      </div>
    </Modal>
  )
}

function TelegramModal({ open, onClose, editTg, botId, onSave }) {
  const isEdit = !!editTg
  const [token, setToken] = useState('')
  const [contacts, setContacts] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (open) {
      setToken('')
      setContacts(editTg?.allowedContacts?.join(', ') ?? '')
      setMessage(editTg?.autoReplyMessage ?? '')
    }
  }, [open, editTg])

  function handleSave() {
    if (!isEdit && !token.trim()) return alert('Token requerido.')
    const allowedContacts = contacts.split(',').map(c => c.trim()).filter(Boolean)
    onSave({ token: token.trim(), allowedContacts, autoReplyMessage: message.trim(), botId, tokenId: editTg?.tokenId })
  }

  return (
    <Modal open={open} onClose={onClose}>
      <h3>{isEdit ? 'Editar Bot de Telegram' : 'Agregar Bot de Telegram'}</h3>
      {!isEdit && (
        <div className="fg">
          <label>Token del bot (de @BotFather)</label>
          <input value={token} onChange={e => setToken(e.target.value)} placeholder="123456789:AAF..." />
        </div>
      )}
      <div className="fg">
        <label>Contactos permitidos (usernames sin @)</label>
        <input value={contacts} onChange={e => setContacts(e.target.value)} placeholder="mi_username, otro_username" />
      </div>
      <div className="fg">
        <label>Mensaje personalizado (opcional)</label>
        <textarea value={message} onChange={e => setMessage(e.target.value)} placeholder="Dejar vacío para usar el de la empresa" />
      </div>
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" onClick={handleSave}>Guardar</button>
      </div>
    </Modal>
  )
}

function MoveModal({ open, onClose, number, sourceBotId, allBots, onMove }) {
  const [targetBotId, setTargetBotId] = useState('')
  const others = allBots.filter(b => b.id !== sourceBotId)

  useEffect(() => {
    if (open && others.length > 0) setTargetBotId(others[0].id)
  }, [open])

  return (
    <Modal open={open} onClose={onClose} width="380px">
      <h3>Mover teléfono</h3>
      <div className="fg">
        <label>Empresa destino</label>
        <select value={targetBotId} onChange={e => setTargetBotId(e.target.value)}>
          {others.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </div>
      <p style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>La sesión de WhatsApp se conserva.</p>
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" onClick={() => onMove(targetBotId)}>Mover</button>
      </div>
    </Modal>
  )
}

function ScreenshotModal({ open, number, onClose, pwd }) {
  const [src, setSrc] = useState(null)
  const [loading, setLoading] = useState(false)
  const [ts, setTs] = useState(null)
  const intervalRef = useRef(null)

  async function fetchShot() {
    if (!number) return
    setLoading(true)
    try {
      const data = await api('GET', `/screenshot/${number}`, null, pwd)
      if (data?.screenshot) { setSrc(data.screenshot); setTs(new Date().toLocaleTimeString()) }
    } catch {}
    setLoading(false)
  }

  useEffect(() => {
    if (!open) { clearInterval(intervalRef.current); setSrc(null); return }
    fetchShot()
    intervalRef.current = setInterval(fetchShot, 8000)
    return () => clearInterval(intervalRef.current)
  }, [open, number])

  return (
    <Modal open={open} onClose={onClose} width="min(92vw, 960px)">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>Browser — +{number}</h3>
        <button className="btn-ghost btn-sm" onClick={fetchShot} disabled={loading}>
          {loading ? '...' : '↺ Refrescar'}
        </button>
        {ts && <span style={{ fontSize: 12, color: '#888', marginLeft: 'auto' }}>Última: {ts} · auto-refresh 8s</span>}
      </div>
      {src
        ? <img
            src={src}
            alt="WA Web"
            style={{ width: '100%', borderRadius: 6, cursor: 'pointer', display: 'block' }}
            onClick={() => window.open(src, '_blank')}
            title="Click para ver en tamaño completo"
          />
        : <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>
            {loading ? 'Capturando...' : 'Sin imagen'}
          </div>
      }
    </Modal>
  )
}

function QRModal({ open, number, onClose, pwd, onConnected }) {
  const [qrSrc, setQrSrc] = useState(null)
  const [status, setStatus] = useState('Iniciando conexión...')
  const [connected, setConnected] = useState(false)
  const stopRef = useRef(null)
  const titleIntervalRef = useRef(null)

  useEffect(() => {
    if (!open || !number) return
    setQrSrc(null)
    setStatus('Iniciando conexión...')
    setConnected(false)

    connectAndPoll({
      number,
      password: pwd,
      onQR(dataUrl) {
        setQrSrc(dataUrl)
        setStatus('El código se renueva cada 20 segundos')
        notifyQR()
      },
      onReady() {
        stopRef.current = null
        setConnected(true)
        setStatus('')
        clearQRNotify()
        setTimeout(() => { onConnected(); onClose() }, 2000)
      },
      onError(msg) {
        setStatus(msg)
        clearQRNotify()
      },
    }).then(stop => { stopRef.current = stop })

    return () => {
      stopRef.current?.()
      clearQRNotify()
    }
  }, [open, number])

  function notifyQR() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      ;[0, 100, 200].forEach(delay => {
        const o = ctx.createOscillator()
        const g = ctx.createGain()
        o.connect(g); g.connect(ctx.destination)
        o.frequency.value = 880
        g.gain.setValueAtTime(0.3, ctx.currentTime + delay / 1000)
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay / 1000 + 0.15)
        o.start(ctx.currentTime + delay / 1000)
        o.stop(ctx.currentTime + delay / 1000 + 0.15)
      })
    } catch {}
    if (titleIntervalRef.current) clearInterval(titleIntervalRef.current)
    const orig = document.title
    let on = true
    titleIntervalRef.current = setInterval(() => {
      document.title = on ? '📱 QR listo!' : orig
      on = !on
    }, 800)
    window.addEventListener('focus', () => {
      clearQRNotify()
      document.title = orig
    }, { once: true })
  }

  function clearQRNotify() {
    if (titleIntervalRef.current) { clearInterval(titleIntervalRef.current); titleIntervalRef.current = null }
  }

  function handleClose() {
    stopRef.current?.()
    clearQRNotify()
    onClose()
  }

  return (
    <Modal open={open} onClose={handleClose} width="360px">
      <div style={{ textAlign: 'center' }}>
        <h3>Vincular +{number}</h3>
        {!connected && (
          <p className="qr-hint">
            Abrí WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong>
          </p>
        )}
        <div className="qr-wrap">
          {connected
            ? <div style={{ fontSize: 48 }}>✅</div>
            : qrSrc ? <img src={qrSrc} alt="QR" /> : <div className="spinner" />
          }
        </div>
        {connected
          ? <div style={{ fontSize: 16, fontWeight: 600, color: '#1a7a45' }}>¡Conectado!</div>
          : <div className="qr-status">{status}</div>
        }
      </div>
    </Modal>
  )
}

// ─── Filas de teléfono / telegram ─────────────────────────────────────────────

function PhoneRow({ phone, botId, simMode, pwd, onConnect, onDisconnect, onEdit, onDelete, onMove, onScreenshot, onDragStart }) {
  const needsQR = ['stopped', 'failed', 'disconnected', 'qr_needed', undefined, null].includes(phone.status)
  const isReady = phone.status === 'ready'
  const contactsText = phone.allowedContacts?.length ? phone.allowedContacts.join(', ') : '(sin contactos permitidos)'

  return (
    <div>
      <div
        className="phone-row"
        draggable
        onDragStart={e => {
          e.dataTransfer.setData('number', phone.number)
          e.dataTransfer.setData('sourceBotId', botId)
          e.dataTransfer.setData('type', 'phone')
          e.currentTarget.classList.add('dragging')
          onDragStart?.()
        }}
        onDragEnd={e => e.currentTarget.classList.remove('dragging')}
      >
        <div className="phone-number">
          <span className="wa-label">WA</span>
          <span className="phone-id">(+{phone.number})</span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="phone-contacts">{contactsText}</div>
          {phone.autoReplyMessage && (
            <div className="phone-msg-override">Mensaje propio: "{phone.autoReplyMessage}"</div>
          )}
        </div>
        <div className="phone-actions">
          {simMode && <span className="badge s-sim">SIM</span>}
          <span className={`badge s-${phone.status}`}>
            <span className="dot" />
            {STATUS_LABELS[phone.status] || phone.status}
          </span>
          {needsQR && !simMode && (
            <button className="btn-primary btn-sm" onClick={() => onConnect(phone.number)}>Vincular QR</button>
          )}
          {needsQR && simMode && (
            <button className="btn-primary btn-sm" onClick={() => onConnect(phone.number)}>Conectar sim</button>
          )}
          {isReady && !simMode && (
            <button className="btn-ghost btn-sm" onClick={() => onScreenshot(phone.number)} title="Ver browser headless">👁 Ver</button>
          )}
          {isReady && (
            <button className="btn-danger btn-sm" onClick={() => onDisconnect(phone.number)}>Desconectar</button>
          )}
          <button className="btn-ghost btn-sm" onClick={() => onMove(phone.number, botId)}>Mover</button>
          <button className="btn-ghost btn-sm" onClick={() => onEdit(phone)}>Editar</button>
          <button className="btn-danger btn-sm" onClick={() => onDelete(phone.number)}>Eliminar</button>
        </div>
      </div>
      {simMode && isReady && (
        <SimChat number={phone.number} pwd={pwd} />
      )}
    </div>
  )
}

function TelegramRow({ tg, botId, simMode, pwd, onEdit, onDelete, onReconnect, onDragStart }) {
  const isReady = tg.status === 'ready'
  const statusClass = isReady ? 's-tg-ready' : `s-${tg.status}`
  const statusLabel = isReady ? 'Activo' : (STATUS_LABELS[tg.status] || tg.status)
  const canReconnect = !simMode && ['stopped', 'failed', 'disconnected'].includes(tg.status)
  const contactsText = tg.allowedContacts?.length ? tg.allowedContacts.join(', ') : '(sin contactos permitidos)'

  return (
    <>
    <div
      className="phone-row phone-row--tg"
      draggable
      onDragStart={e => {
        e.dataTransfer.setData('tokenId', tg.tokenId)
        e.dataTransfer.setData('sourceBotId', botId)
        e.dataTransfer.setData('type', 'telegram')
        e.currentTarget.classList.add('dragging')
        onDragStart?.()
      }}
      onDragEnd={e => e.currentTarget.classList.remove('dragging')}
    >
      <div className="phone-number">
        <span className="tg-label">TG</span>
        <span className="phone-id">({tg.tokenId})</span>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="phone-contacts">{contactsText}</div>
        {tg.autoReplyMessage && (
          <div className="phone-msg-override">Mensaje propio: "{tg.autoReplyMessage}"</div>
        )}
      </div>
      <div className="phone-actions">
        <span className={`badge ${statusClass}`}>
          <span className="dot" />
          {statusLabel}
        </span>
        {canReconnect && (
          <button className="btn-blue btn-sm" onClick={() => onReconnect(tg.tokenId)}>Reconectar</button>
        )}
        <button className="btn-ghost btn-sm" onClick={() => onEdit(tg)}>Editar</button>
        <button className="btn-danger btn-sm" onClick={() => onDelete(tg.tokenId)}>Eliminar</button>
      </div>
    </div>
    {simMode && isReady && <SimChat number={tg.sessionId} pwd={pwd} />}
    </>
  )
}

// ─── Dashboard principal ───────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate()
  const pwd = sessionStorage.getItem('admin_pwd') || ''

  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshLabel, setRefreshLabel] = useState('↺ Refresh')
  const [simMode, setSimMode] = useState(false)

  // Modales
  const [botModal, setBotModal] = useState({ open: false, editBot: null })
  const [phoneModal, setPhoneModal] = useState({ open: false, editPhone: null, botId: null })
  const [tgModal, setTgModal] = useState({ open: false, editTg: null, botId: null })
  const [moveModal, setMoveModal] = useState({ open: false, number: null, sourceBotId: null })
  const [qrModal, setQrModal] = useState({ open: false, number: null })
  const [screenshotModal, setScreenshotModal] = useState({ open: false, number: null })

  // Redirect si no hay pwd
  useEffect(() => {
    if (!pwd) navigate('/')
  }, [pwd, navigate])

  const call = useCallback(
    (method, path, body) => api(method, path, body, pwd),
    [pwd]
  )

  const loadBots = useCallback(async () => {
    const data = await call('GET', '/bots')
    if (Array.isArray(data)) setBots(data)
    setLoading(false)
  }, [call])

  useEffect(() => {
    if (!pwd) return
    api('GET', '/mode', null, pwd).then(data => {
      if (data?.mode === 'sim') setSimMode(true)
    })
    loadBots()
    const interval = setInterval(loadBots, 6000)
    return () => clearInterval(interval)
  }, [loadBots, pwd])

  function logout() {
    sessionStorage.removeItem('admin_pwd')
    navigate('/')
  }

  async function handleRefresh() {
    setRefreshLabel('Reconectando...')
    const res = await call('POST', '/refresh')
    await loadBots()
    const label = res.reconnected > 0 ? `↺ Refresh (${res.reconnected})` : '↺ Refresh'
    setRefreshLabel(label)
    setTimeout(() => setRefreshLabel('↺ Refresh'), 3000)
  }

  function copyLink() {
    navigator.clipboard.writeText(window.location.origin + '/connect')
  }

  // ── Bot CRUD ──
  async function handleSaveBot({ id, name, autoReplyMessage }) {
    const isEdit = !!botModal.editBot
    let res
    if (isEdit) {
      res = await call('PUT', `/bots/${botModal.editBot.id}`, { name, autoReplyMessage })
    } else {
      // Crear empresa requiere al menos un teléfono — abrimos modal de teléfono
      setBotModal({ open: false, editBot: null })
      setPhoneModal({ open: true, editPhone: null, botId: id, newBotData: { name, autoReplyMessage } })
      return
    }
    if (res.error) return alert('Error: ' + res.error)
    setBotModal({ open: false, editBot: null })
    loadBots()
  }

  async function handleDeleteBot(botId) {
    const bot = bots.find(b => b.id === botId)
    if (!confirm(`¿Eliminar la empresa "${bot?.name || botId}" y todos sus teléfonos?`)) return
    const res = await call('DELETE', `/bots/${botId}`)
    if (res.error) return alert('Error: ' + res.error)
    loadBots()
  }

  // ── Phone CRUD ──
  async function handleSavePhone({ number, allowedContacts, autoReplyMessage, botId }) {
    const isEdit = !!phoneModal.editPhone
    let res
    if (isEdit) {
      res = await call('PUT', `/phones/${phoneModal.editPhone.number}`, { allowedContacts, autoReplyMessage })
    } else {
      const body = { botId, number, allowedContacts }
      if (autoReplyMessage) body.autoReplyMessage = autoReplyMessage
      if (phoneModal.newBotData) {
        body.botName = phoneModal.newBotData.name
        if (!body.autoReplyMessage) body.autoReplyMessage = phoneModal.newBotData.autoReplyMessage
      }
      res = await call('POST', '/phones', body)
    }
    if (res.error) return alert('Error: ' + res.error)
    setPhoneModal({ open: false, editPhone: null, botId: null })
    loadBots()
  }

  async function handleDeletePhone(number) {
    if (!confirm(`¿Eliminar el teléfono +${number}?`)) return
    const res = await call('DELETE', `/phones/${number}`)
    if (res.error) return alert('Error: ' + res.error)
    loadBots()
  }

  // ── Telegram CRUD ──
  async function handleSaveTg({ token, allowedContacts, autoReplyMessage, botId, tokenId }) {
    const isEdit = !!tgModal.editTg
    let res
    if (isEdit) {
      res = await call('PUT', `/telegram/${tokenId}`, { allowedContacts, autoReplyMessage })
    } else {
      const body = { botId, token, allowedContacts }
      if (autoReplyMessage) body.autoReplyMessage = autoReplyMessage
      res = await call('POST', '/telegram', body)
    }
    if (res.error) return alert('Error: ' + res.error)
    setTgModal({ open: false, editTg: null, botId: null })
    loadBots()
  }

  async function handleDeleteTg(tokenId) {
    if (!confirm(`¿Eliminar el bot de Telegram con token ID ${tokenId}?`)) return
    const res = await call('DELETE', `/telegram/${tokenId}`)
    if (res.error) return alert('Error: ' + res.error)
    loadBots()
  }

  async function handleReconnectTg(tokenId) {
    const res = await call('POST', `/telegram/connect/${tokenId}`)
    if (res.error) return alert('Error: ' + res.error)
    setTimeout(loadBots, 2000)
  }

  async function handleConnect(number) {
    if (simMode) {
      const res = await call('POST', `/sim/connect/${number}`)
      if (res.error) return alert('Error: ' + res.error)
      loadBots()
    } else {
      setQrModal({ open: true, number })
    }
  }

  async function handleDisconnect(number) {
    const res = simMode
      ? await call('POST', `/sim/disconnect/${number}`)
      : await call('POST', `/disconnect/${number}`)
    if (res.error) return alert('Error: ' + res.error)
    loadBots()
  }

  // ── Mover ──
  async function handleMovePhone(targetBotId) {
    const res = await call('POST', `/phones/${moveModal.number}/move`, { targetBotId })
    if (res.error) return alert('Error: ' + res.error)
    setMoveModal({ open: false, number: null, sourceBotId: null })
    loadBots()
  }

  // ── Drag & drop ──
  async function onDrop(e, targetBotId) {
    e.preventDefault()
    document.querySelectorAll('.bot-block').forEach(el => el.classList.remove('drag-over'))
    const type = e.dataTransfer.getData('type')
    const sourceBotId = e.dataTransfer.getData('sourceBotId')
    if (sourceBotId === targetBotId) return

    if (type === 'telegram') {
      const tokenId = e.dataTransfer.getData('tokenId')
      if (!tokenId) return
      const res = await call('POST', `/telegram/${tokenId}/move`, { targetBotId })
      if (res.error) return alert('Error: ' + res.error)
    } else {
      const number = e.dataTransfer.getData('number')
      if (!number) return
      const res = await call('POST', `/phones/${number}/move`, { targetBotId })
      if (res.error) return alert('Error: ' + res.error)
    }
    loadBots()
  }

  // ── Render ──
  return (
    <>
      <header>
        <span>📱 Bot Farm — Admin</span>
        <div className="header-actions">
          <button className="btn-ghost btn-sm" onClick={handleRefresh} disabled={refreshLabel !== '↺ Refresh'}>
            {refreshLabel}
          </button>
          <button className="btn-ghost btn-sm" onClick={logout}>Salir</button>
        </div>
      </header>

      <main>
        {/* Link para clientes */}
        <div className="card">
          <div className="card-title">Link para conectar clientes</div>
          <div className="share-row">
            <input className="share-url" readOnly value={window.location.origin + '/connect'} />
            <button className="btn-blue" onClick={copyLink}>Copiar</button>
            <button className="btn-ghost" onClick={() => window.open(window.location.origin + '/connect')}>Abrir</button>
          </div>
        </div>

        {/* Empresas */}
        <div className="card">
          <div className="section-header">
            <h2>Empresas y teléfonos</h2>
            <button className="btn-primary btn-sm" onClick={() => setBotModal({ open: true, editBot: null })}>
              + Nueva empresa
            </button>
          </div>

          {loading && <div className="empty">Cargando...</div>}
          {!loading && bots.length === 0 && (
            <div className="empty">No hay empresas configuradas. Creá una con el botón de arriba.</div>
          )}

          {bots.map(bot => (
            <div
              key={bot.id}
              className="bot-block"
              onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag-over') }}
              onDragLeave={e => e.currentTarget.classList.remove('drag-over')}
              onDrop={e => onDrop(e, bot.id)}
            >
              <div className="bot-header">
                <div className="bot-header-info">
                  <div className="bot-name">{bot.name}</div>
                  <div className="bot-id">{bot.id}</div>
                  <div className="bot-msg">{bot.autoReplyMessage}</div>
                </div>
                <div className="bot-header-actions">
                  <button className="btn-ghost btn-sm" onClick={() => setBotModal({ open: true, editBot: bot })}>
                    Editar
                  </button>
                  <button className="btn-danger btn-sm" onClick={() => handleDeleteBot(bot.id)}>
                    Eliminar
                  </button>
                </div>
              </div>

              <div className="phones-table">
                {bot.phones?.length === 0 && (bot.telegram?.length === 0) && (
                  <div className="empty" style={{ padding: 12 }}>Sin canales configurados</div>
                )}

                {bot.phones?.length > 0 && (
                  <>
                    <div className="channel-header channel-header--wa">WhatsApp</div>
                    {bot.phones.map(p => (
                      <PhoneRow
                        key={p.number}
                        phone={p}
                        botId={bot.id}
                        simMode={simMode}
                        pwd={pwd}
                        onConnect={handleConnect}
                        onDisconnect={handleDisconnect}
                        onEdit={phone => setPhoneModal({ open: true, editPhone: phone, botId: bot.id })}
                        onDelete={handleDeletePhone}
                        onMove={(number, srcBotId) => setMoveModal({ open: true, number, sourceBotId: srcBotId })}
                        onScreenshot={number => setScreenshotModal({ open: true, number })}
                      />
                    ))}
                  </>
                )}

                {bot.telegram?.length > 0 && (
                  <>
                    <div className="channel-header channel-header--tg">Telegram</div>
                    {bot.telegram.map(tg => (
                      <TelegramRow
                        key={tg.tokenId}
                        tg={tg}
                        botId={bot.id}
                        simMode={simMode}
                        pwd={pwd}
                        onEdit={t => setTgModal({ open: true, editTg: t, botId: bot.id })}
                        onDelete={handleDeleteTg}
                        onReconnect={handleReconnectTg}
                      />
                    ))}
                  </>
                )}
              </div>

              <div className="add-phone-row">
                <button className="btn-blue btn-sm" onClick={() => setPhoneModal({ open: true, editPhone: null, botId: bot.id })}>
                  + WhatsApp
                </button>
                <button className="btn-sm" style={{ background: '#e3f2fd', color: '#0d47a1' }}
                  onClick={() => setTgModal({ open: true, editTg: null, botId: bot.id })}>
                  + Telegram
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* Modales */}
      <BotModal
        open={botModal.open}
        editBot={botModal.editBot}
        onClose={() => setBotModal({ open: false, editBot: null })}
        onSave={handleSaveBot}
      />

      <PhoneModal
        open={phoneModal.open}
        editPhone={phoneModal.editPhone}
        botId={phoneModal.botId}
        allBots={bots}
        onClose={() => setPhoneModal({ open: false, editPhone: null, botId: null })}
        onSave={handleSavePhone}
      />

      <TelegramModal
        open={tgModal.open}
        editTg={tgModal.editTg}
        botId={tgModal.botId}
        onClose={() => setTgModal({ open: false, editTg: null, botId: null })}
        onSave={handleSaveTg}
      />

      <MoveModal
        open={moveModal.open}
        number={moveModal.number}
        sourceBotId={moveModal.sourceBotId}
        allBots={bots}
        onClose={() => setMoveModal({ open: false, number: null, sourceBotId: null })}
        onMove={handleMovePhone}
      />

      <QRModal
        open={qrModal.open}
        number={qrModal.number}
        pwd={pwd}
        onClose={() => setQrModal({ open: false, number: null })}
        onConnected={loadBots}
      />

      <ScreenshotModal
        open={screenshotModal.open}
        number={screenshotModal.number}
        pwd={pwd}
        onClose={() => setScreenshotModal({ open: false, number: null })}
      />
    </>
  )
}
