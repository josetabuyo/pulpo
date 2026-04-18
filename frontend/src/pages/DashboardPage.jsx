import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, connectAndPoll } from '../api.js'
import MonitorPanel from '../components/MonitorPanel.jsx'
import EmpresaCard, { normalizeBot } from '../components/EmpresaCard.jsx'

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

  useEffect(() => {
    if (open) {
      setId(editBot?.id ?? '')
      setName(editBot?.name ?? '')
    }
  }, [open, editBot])

  function handleSave() {
    if (!name.trim()) return alert('Nombre requerido.')
    if (!isEdit && !id.trim()) return alert('ID es requerido.')
    onSave({ id: id.trim(), name: name.trim() })
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
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" onClick={handleSave}>Guardar</button>
      </div>
    </Modal>
  )
}

function PhoneModal({ open, onClose, botId, newBotData, onSave }) {
  const [number, setNumber] = useState('')

  useEffect(() => {
    if (open) setNumber('')
  }, [open])

  function handleSave() {
    if (!number.trim()) return alert('Número requerido.')
    onSave({ number: number.trim(), botId })
  }

  return (
    <Modal open={open} onClose={onClose}>
      <h3>Agregar teléfono</h3>
      <div className="fg">
        <label>Número (sin +)</label>
        <input type="tel" value={number} onChange={e => setNumber(e.target.value)} placeholder="5491155612767" />
      </div>
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" onClick={handleSave}>Guardar</button>
      </div>
    </Modal>
  )
}

function TelegramModal({ open, onClose, botId, onSave }) {
  const [token, setToken] = useState('')

  useEffect(() => {
    if (open) setToken('')
  }, [open])

  function handleSave() {
    if (!token.trim()) return alert('Token requerido.')
    onSave({ token: token.trim(), botId })
  }

  return (
    <Modal open={open} onClose={onClose}>
      <h3>Agregar Bot de Telegram</h3>
      <div className="fg">
        <label>Token del bot (de @BotFather)</label>
        <input value={token} onChange={e => setToken(e.target.value)} placeholder="123456789:AAF..." />
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
    const base = 'Pulpo — Dashboard'
    let on = true
    titleIntervalRef.current = setInterval(() => {
      document.title = on ? '📱 QR listo!' : base
      on = !on
    }, 800)
    window.addEventListener('focus', () => {
      clearQRNotify()
      document.title = base
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

// ─── Dashboard principal ───────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate()
  const pwd = sessionStorage.getItem('admin_pwd') || ''

  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshLabel, setRefreshLabel] = useState('↺ Refresh')
  const [syncLabel, setSyncLabel] = useState('⟳ Re-Sync')
  const [syncRunning, setSyncRunning] = useState(false)
  const [recentSyncLabel, setRecentSyncLabel] = useState('↑ Actualizar')
  const [simMode, setSimMode] = useState(false)
  const [fbSessionLabel, setFbSessionLabel] = useState('FB Sesión')
  const [fbSessionRunning, setFbSessionRunning] = useState(false)

  // Modales
  const [botModal, setBotModal] = useState({ open: false, editBot: null })
  const [phoneModal, setPhoneModal] = useState({ open: false, botId: null, newBotData: null })
  const [tgModal, setTgModal] = useState({ open: false, botId: null })
  const [moveModal, setMoveModal] = useState({ open: false, number: null, sourceBotId: null })
  const [qrModal, setQrModal] = useState({ open: false, number: null })
  const [screenshotModal, setScreenshotModal] = useState({ open: false, number: null })
  const [expandedBot, setExpandedBot] = useState(null)
  const [monitorAlerts,     setMonitorAlerts]     = useState(0)
  const [monitorCollapsed,  setMonitorCollapsed]  = useState(true)
  const [companiesCollapsed, setCompaniesCollapsed] = useState(false)

  useEffect(() => { document.title = 'Pulpo — Dashboard' }, [])

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

    // Polling del estado de sync para mantener botón deshabilitado mientras corre
    const syncInterval = setInterval(async () => {
      const s = await api('GET', '/sync-status', null, pwd).catch(() => null)
      if (!s) return
      setSyncRunning(prev => {
        if (prev && !s.running) {
          setSyncLabel('✓ Listo')
          setTimeout(() => setSyncLabel('⟳ Re-Sync'), 3000)
        }
        return s.running
      })
    }, 3000)

    return () => { clearInterval(interval); clearInterval(syncInterval) }
  }, [loadBots, pwd])

  function logout() {
    sessionStorage.removeItem('admin_pwd')
    navigate('/')
  }

  async function handleFbSession(pageId = 'luganense') {
    if (fbSessionRunning) return
    setFbSessionRunning(true)
    setFbSessionLabel('Abriendo browser…')
    try {
      const res = await call('POST', `/fb/refresh-session?page_id=${pageId}`, {})
      if (!res.ok) {
        setFbSessionLabel('⚠ ' + (res.message || 'Error'))
        setTimeout(() => { setFbSessionLabel('FB Sesión'); setFbSessionRunning(false) }, 5000)
        return
      }
      // Polling del estado hasta que termine
      setFbSessionLabel('Esperando login…')
      const poll = setInterval(async () => {
        try {
          const st = await call('GET', `/fb/session-status?page_id=${pageId}`, null)
          if (st.state === 'ok') {
            setFbSessionLabel('✓ Sesión renovada')
            clearInterval(poll)
            setTimeout(() => { setFbSessionLabel('FB Sesión'); setFbSessionRunning(false) }, 4000)
          } else if (st.state === 'error') {
            setFbSessionLabel('⚠ ' + (st.message || 'Error'))
            clearInterval(poll)
            setTimeout(() => { setFbSessionLabel('FB Sesión'); setFbSessionRunning(false) }, 5000)
          }
        } catch { clearInterval(poll); setFbSessionLabel('FB Sesión'); setFbSessionRunning(false) }
      }, 3000)
      // Timeout máximo 130s
      setTimeout(() => { clearInterval(poll); if (fbSessionRunning) { setFbSessionLabel('FB Sesión'); setFbSessionRunning(false) } }, 130_000)
    } catch {
      setFbSessionLabel('⚠ Error')
      setTimeout(() => { setFbSessionLabel('FB Sesión'); setFbSessionRunning(false) }, 4000)
    }
  }

  async function handleRefresh() {
    setRefreshLabel('Reconectando...')
    const res = await call('POST', '/refresh')
    await loadBots()
    const label = res.reconnected > 0 ? `↺ Refresh (${res.reconnected})` : '↺ Refresh'
    setRefreshLabel(label)
    setTimeout(() => setRefreshLabel('↺ Refresh'), 3000)
  }

  async function handleFullSync() {
    setSyncLabel('Sincronizando...')
    setSyncRunning(true)
    await call('POST', '/full-sync')
  }

  async function handleRecentSync() {
    setRecentSyncLabel('Actualizando...')
    await call('POST', '/recent-sync')
    setRecentSyncLabel('✓ Listo')
    setTimeout(() => setRecentSyncLabel('↑ Actualizar'), 4000)
  }

  function copyLink() {
    navigator.clipboard.writeText(window.location.origin + '/connect')
  }

  // ── Bot CRUD ──
  async function handleSaveBot({ id, name }) {
    const isEdit = !!botModal.editBot
    let res
    if (isEdit) {
      res = await call('PUT', `/bots/${botModal.editBot.id}`, { name })
    } else {
      // Crear empresa requiere al menos un teléfono — abrimos modal de teléfono
      setBotModal({ open: false, editBot: null })
      setPhoneModal({ open: true, botId: id, newBotData: { name } })
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
  async function handleSavePhone({ number, botId }) {
    const body = { botId, number }
    if (phoneModal.newBotData) body.botName = phoneModal.newBotData.name
    const res = await call('POST', '/phones', body)
    if (res.error) return alert('Error: ' + res.error)
    setPhoneModal({ open: false, botId: null, newBotData: null })
    loadBots()
  }

  async function handleDeletePhone(number) {
    if (!confirm(`¿Eliminar el teléfono +${number}?`)) return
    const res = await call('DELETE', `/phones/${number}`)
    if (res.error) return alert('Error: ' + res.error)
    loadBots()
  }

  // ── Telegram CRUD ──
  async function handleSaveTg({ token, botId }) {
    const res = await call('POST', '/telegram', { botId, token })
    if (res.error) return alert('Error: ' + res.error)
    setTgModal({ open: false, botId: null })
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
    document.querySelectorAll('.ec-card').forEach(el => el.classList.remove('drag-over'))
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
        <span>🐙 Pulpo — Admin</span>
        <div className="header-actions">
          <button className="btn-ghost btn-sm" onClick={handleRefresh} disabled={refreshLabel !== '↺ Refresh'}>
            {refreshLabel}
          </button>
          <button
            className="btn-ghost btn-sm"
            onClick={() => handleFbSession('luganense')}
            disabled={fbSessionRunning}
            title="Renovar cookies de Facebook (abre browser en el servidor)"
          >
            {fbSessionLabel}
          </button>
          <button className="btn-ghost btn-sm" onClick={handleRecentSync} disabled={recentSyncLabel === 'Actualizando...'} title="Captura los mensajes recientes visibles en cada chat (sin scroll histórico). Ideal tras un reinicio.">
            {recentSyncLabel}
          </button>
          <button className="btn-ghost btn-sm" onClick={handleFullSync} disabled={syncRunning} title="Scrapea historial completo de todos los contactos WA">
            {syncLabel}
          </button>
          <button className="btn-ghost btn-sm" onClick={logout}>Salir</button>
        </div>
      </header>

      <main>

        {/* ── Sección: Monitor ── */}
        <div className="section-block">
          <div className="section-block-header" onClick={() => setMonitorCollapsed(c => !c)}>
            <div className="section-block-title">
              📊 Monitor
              {monitorAlerts > 0 && <span className="mon-badge-inline">{monitorAlerts} alertas</span>}
            </div>
            <button
              className="btn-ghost btn-sm"
              onClick={e => { e.stopPropagation(); setMonitorCollapsed(c => !c) }}
            >{monitorCollapsed ? '▼ Expandir' : '▲ Colapsar'}</button>
          </div>
          <div style={{ display: monitorCollapsed ? 'none' : 'block' }}>
            <MonitorPanel pwd={pwd} onAlertsChange={setMonitorAlerts} active={!monitorCollapsed} />
          </div>
        </div>

        {/* ── Links para clientes ── */}
        <div className="card">
          <div className="card-title">Links para empresas</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>Portal de empresa (acceso con contraseña)</div>
              <div className="share-row">
                <input className="share-url" readOnly value={(import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/empresa'} />
                <button className="btn-blue" onClick={() => navigator.clipboard.writeText((import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/empresa')}>Copiar</button>
                <button className="btn-ghost" onClick={() => window.open((import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/empresa')}>Abrir</button>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>Alta nueva empresa (link en blanco)</div>
              <div className="share-row">
                <input className="share-url" readOnly value={(import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/empresa/nueva'} />
                <button className="btn-blue" onClick={() => navigator.clipboard.writeText((import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/empresa/nueva')}>Copiar</button>
                <button className="btn-ghost" onClick={() => window.open((import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/empresa/nueva')}>Abrir</button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Sección: Empresas ── */}
        <div className="section-block">
          <div className="section-block-header" onClick={() => setCompaniesCollapsed(c => !c)}>
            <div className="section-block-title">🏢 Empresas y teléfonos</div>
            <div className="section-block-actions" onClick={e => e.stopPropagation()}>
              <button className="btn-primary btn-sm" onClick={() => setBotModal({ open: true, editBot: null })}>
                + Nueva empresa
              </button>
              <button
                className="btn-ghost btn-sm"
                onClick={() => setCompaniesCollapsed(c => !c)}
              >{companiesCollapsed ? '▼ Expandir' : '▲ Colapsar'}</button>
            </div>
          </div>
          {!companiesCollapsed && (
        <div className="section-body">

          {loading && <div className="empty">Cargando...</div>}
          {!loading && bots.length === 0 && (
            <div className="empty">No hay empresas configuradas. Creá una con el botón de arriba.</div>
          )}

          {bots.map(bot => (
            <EmpresaCard
              key={bot.id}
              mode="admin"
              bot={normalizeBot(bot)}
              onExpand={b => setExpandedBot({ bot, normalized: b })}
              simMode={simMode}
              apiCall={(method, path, body) => call(method, path, body)}
              adminPwd={pwd}
              onRefresh={loadBots}
              onEditBot={b => setBotModal({ open: true, editBot: b })}
              onDeleteBot={botId => handleDeleteBot(botId)}
              onAddPhone={botId => setPhoneModal({ open: true, botId })}
              onAddTelegram={botId => setTgModal({ open: true, botId })}
              onDeletePhone={conn => handleDeletePhone(conn.number)}
              onMovePhone={conn => setMoveModal({ open: true, number: conn.number, sourceBotId: bot.id })}
              onDeleteTelegram={conn => handleDeleteTg(conn.number)}
              onReconnectTg={conn => handleReconnectTg(conn.number)}
              onConnectWA={conn => handleConnect(conn.number)}
              onDisconnectWA={conn => handleDisconnect(conn.number)}
              onScreenshot={conn => setScreenshotModal({ open: true, number: conn.number })}
              onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag-over') }}
              onDragLeave={e => e.currentTarget.classList.remove('drag-over')}
              onDrop={e => onDrop(e, bot.id)}
            />
          ))}
        </div>
          )}
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
        botId={phoneModal.botId}
        newBotData={phoneModal.newBotData}
        onClose={() => setPhoneModal({ open: false, botId: null, newBotData: null })}
        onSave={handleSavePhone}
      />

      <TelegramModal
        open={tgModal.open}
        botId={tgModal.botId}
        onClose={() => setTgModal({ open: false, botId: null })}
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

      {/* Modal fullscreen de empresa expandida */}
      {expandedBot && (
        <div
          className="overlay open"
          onClick={e => e.target === e.currentTarget && setExpandedBot(null)}
        >
          <div className="modal" style={{ width: '92vw', maxWidth: '1200px', height: '90vh', overflowY: 'auto', padding: 0, paddingTop: 40 }}>
            <button className="modal-close" onClick={() => setExpandedBot(null)}>✕</button>
            <EmpresaCard
              mode="admin"
              bot={expandedBot.normalized}
              simMode={simMode}
              apiCall={(method, path, body) => call(method, path, body)}
              adminPwd={pwd}
              onRefresh={loadBots}
              onEditBot={b => { setExpandedBot(null); setBotModal({ open: true, editBot: b }) }}
              onDeleteBot={botId => { setExpandedBot(null); handleDeleteBot(botId) }}
              onAddPhone={botId => setPhoneModal({ open: true, botId })}
              onAddTelegram={botId => setTgModal({ open: true, botId })}
              onDeletePhone={conn => handleDeletePhone(conn.number)}
              onMovePhone={conn => setMoveModal({ open: true, number: conn.number, sourceBotId: expandedBot.bot.id })}
              onDeleteTelegram={conn => handleDeleteTg(conn.number)}
              onReconnectTg={conn => handleReconnectTg(conn.number)}
              onConnectWA={conn => handleConnect(conn.number)}
              onDisconnectWA={conn => handleDisconnect(conn.number)}
              onScreenshot={conn => setScreenshotModal({ open: true, number: conn.number })}
            />
          </div>
        </div>
      )}

    </>
  )
}
