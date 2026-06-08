import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
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
  const [tgModal, setTgModal] = useState({ open: false, botId: null })
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
    const res = isEdit
      ? await call('PUT', `/bots/${botModal.editBot.id}`, { name })
      : await call('POST', '/bots', { id, name })
    if (res.error) return alert('Error: ' + res.error)
    setBotModal({ open: false, editBot: null })
    loadBots()
  }

  async function handleDeleteBot(botId) {
    const bot = bots.find(b => b.id === botId)
    if (!confirm(`¿Eliminar la empresa "${bot?.name || botId}"?`)) return
    const res = await call('DELETE', `/bots/${botId}`)
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

  // ── Drag & drop ──
  async function onDrop(e, targetBotId) {
    e.preventDefault()
    document.querySelectorAll('.ec-card').forEach(el => el.classList.remove('drag-over'))
    const sourceBotId = e.dataTransfer.getData('sourceBotId')
    if (sourceBotId === targetBotId) return
    const tokenId = e.dataTransfer.getData('tokenId')
    if (!tokenId) return
    const res = await call('POST', `/telegram/${tokenId}/move`, { targetBotId })
    if (res.error) return alert('Error: ' + res.error)
    loadBots()
  }

  // ── Render ──
  return (
    <>
      <header>
        <span>🐙 Pulpo — Admin</span>
        <div className="header-actions">
          <button className="btn-ghost btn-sm" onClick={handleRefresh} disabled={refreshLabel !== '↺ Refresh'} title="Reconectar bots de Telegram">
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
          <button className="btn-ghost btn-sm" onClick={handleFullSync} disabled={syncRunning} title="Re-sincronizar historial">
            {syncLabel}
          </button>
          <button className="btn-ghost btn-sm" onClick={logout} title="Cerrar sesión">Salir</button>
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
            <div className="section-block-title">🏢 Empresas</div>
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
              apiCall={call}
              onRefresh={loadBots}
              onEditBot={b => setBotModal({ open: true, editBot: b })}
              onDeleteBot={botId => handleDeleteBot(botId)}
              onAddTelegram={botId => setTgModal({ open: true, botId })}
              onDeleteTelegram={conn => handleDeleteTg(conn.number)}
              onReconnectTg={conn => handleReconnectTg(conn.number)}
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

      <TelegramModal
        open={tgModal.open}
        botId={tgModal.botId}
        onClose={() => setTgModal({ open: false, botId: null })}
        onSave={handleSaveTg}
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
              apiCall={call}
              onRefresh={loadBots}
              onEditBot={b => { setExpandedBot(null); setBotModal({ open: true, editBot: b }) }}
              onDeleteBot={botId => { setExpandedBot(null); handleDeleteBot(botId) }}
              onAddTelegram={botId => setTgModal({ open: true, botId })}
              onDeleteTelegram={conn => handleDeleteTg(conn.number)}
              onReconnectTg={conn => handleReconnectTg(conn.number)}
            />
          </div>
        </div>
      )}

    </>
  )
}
