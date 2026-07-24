import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, apiQuiet } from '../api.js'
import MonitorPanel from '../components/MonitorPanel.jsx'
import BotCard, { normalizeBot } from '../components/BotCard.jsx'

// ─── WaviModal ────────────────────────────────────────────────────────────────

function WaviModal({ open, onClose, session }) {
  const [sessions, setSessions] = useState([])
  const [starting, setStarting] = useState(false)
  const [qrHtml, setQrHtml] = useState('')

  useEffect(() => {
    if (!open) return
    setSessions([])
    setStarting(false)
    setQrHtml('')
    const fetchSessions = () => apiQuiet('GET', '/wavi/sessions', null).then(s => { if (s) setSessions(s) })
    fetchSessions()
    const id = setInterval(fetchSessions, 3000)
    return () => clearInterval(id)
  }, [open, session])

  useEffect(() => {
    if (!open) return
    const fetchQr = async () => {
      try {
        const res = await fetch('/api/wavi/qr-page', { credentials: 'include' })
        if (res.ok) setQrHtml(await res.text())
      } catch (e) {
        // El polling reintenta solo en el próximo tick; el rastro queda en consola
        console.warn('[DashboardPage] fetch de QR falló', e)
      }
    }
    fetchQr()
    const id = setInterval(fetchQr, 5000)
    return () => clearInterval(id)
  }, [open])

  const isSpecificSession = session && session !== 'default'

  async function handleConnect() {
    setStarting(true)
    if (isSpecificSession) {
      await apiQuiet('POST', `/wavi/sessions/${session}/connect`, null)
    } else {
      await apiQuiet('POST', '/wavi/sessions', { session: null })
    }
    setStarting(false)
  }

  const visibleSessions = isSpecificSession
    ? sessions.filter(s => s.session === session)
    : sessions

  return (
    <div className={`overlay${open ? ' open' : ''}`} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ width: 420 }}>
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3>{isSpecificSession ? `Conectar WhatsApp — ${session}` : 'Conectar WhatsApp (Wavi)'}</h3>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 0 }}>
          {isSpecificSession
            ? 'Iniciá el daemon y escaneá el QR con tu celular para reconectar esta sesión.'
            : 'Iniciá el daemon y escaneá el QR con tu celular.'}
        </p>
        <button className="btn-primary" onClick={handleConnect} disabled={starting} style={{ marginBottom: 12 }}>
          {starting ? 'Iniciando…' : isSpecificSession ? '↻ Reconectar + QR' : '▶ Iniciar daemon + QR'}
        </button>
        <iframe
          srcDoc={qrHtml}
          style={{ width: '100%', height: 360, border: '1px solid var(--border)', borderRadius: 6 }}
          title="WhatsApp QR"
        />
        {visibleSessions.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Estado</div>
            {visibleSessions.map(s => (
              <div key={s.session} style={{ fontSize: 12, color: s.authenticated ? 'var(--success)' : 'var(--text-muted)', marginBottom: 2 }}>
                {s.session}: {s.authenticated ? '✓ Conectado' : s.connecting ? '⏳ Conectando…' : 'Detenido'}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Modales inline ────────────────────────────────────────────────────────────

function Modal({ open, onClose, width, children }) {
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
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (open) {
      setId(editBot?.id ?? '')
      setName(editBot?.name ?? '')
      setPassword('')
    }
  }, [open, editBot])

  function handleSave() {
    if (!name.trim()) return alert('Nombre requerido.')
    if (!isEdit && !id.trim()) return alert('ID es requerido.')
    if (!isEdit && !password.trim()) return alert('Contraseña requerida.')
    onSave({ id: id.trim(), name: name.trim(), password: password.trim() })
  }

  return (
    <Modal open={open} onClose={onClose}>
      <h3>{isEdit ? 'Editar bot' : 'Nueva bot'}</h3>
      {!isEdit && (
        <div className="fg">
          <label>ID (sin espacios, ej: bot_guardia)</label>
          <input value={id} onChange={e => setId(e.target.value)} placeholder="bot_guardia" />
        </div>
      )}
      <div className="fg">
        <label>Nombre de la bot</label>
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Herrería García" />
      </div>
      {!isEdit && (
        <div className="fg">
          <label>Contraseña de acceso</label>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Clave para que la bot acceda al portal" />
        </div>
      )}
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
  const [searchParams, setSearchParams] = useSearchParams()

  const [bots, setBots] = useState([])
  const [loading, setLoading] = useState(true)

  // Modales
  const [botModal, setBotModal] = useState({ open: false, editBot: null })
  const [tgModal, setTgModal] = useState({ open: false, botId: null })
  const [expandedBot, setExpandedBot] = useState(null)
  const [monitorCollapsed,  setMonitorCollapsed]  = useState(() => searchParams.get('monitor') !== '1')
  const [companiesCollapsed, setCompaniesCollapsed] = useState(false)
  const [waviModal,         setWaviModal]          = useState({ open: false, session: null })

  useEffect(() => { document.title = 'Pulpo — Dashboard' }, [])

  // La sesión ya se valida en RequireAuth (App.jsx) antes de montar esta página.
  const call = useCallback(
    (method, path, body) => api(method, path, body),
    []
  )

  const loadBots = useCallback(async () => {
    const data = await call('GET', '/bots')
    if (Array.isArray(data)) setBots(data)
    setLoading(false)
  }, [call])

  useEffect(() => {
    loadBots()
    const interval = setInterval(loadBots, 6000)
    return () => clearInterval(interval)
  }, [loadBots])

  useEffect(() => {
    const botId = searchParams.get('bot')
    if (!botId || !bots.length || expandedBot) return
    const bot = bots.find(b => b.id === botId)
    if (bot) setExpandedBot({ bot, normalized: normalizeBot(bot) })
  }, [bots, searchParams, expandedBot])

  function logout() {
    window.location.href = '/api/auth/signout?callbackUrl=/'
  }

  function toggleSection(key, collapsed, setCollapsed) {
    const next = !collapsed
    setCollapsed(next)
    setSearchParams(prev => {
      const p = new URLSearchParams(prev)
      if (!next) p.set(key, '1')
      else p.delete(key)
      return p
    }, { replace: true })
  }

  function openBotModal(botData) {
    setExpandedBot(botData)
    setSearchParams(prev => {
      const p = new URLSearchParams(prev)
      if (botData) p.set('bot', botData.bot.id)
      else p.delete('bot')
      return p
    }, { replace: true })
  }

  // ── Bot CRUD ──
  async function handleSaveBot({ id, name, password }) {
    const isEdit = !!botModal.editBot
    const res = isEdit
      ? await call('PUT', `/bots/${botModal.editBot.id}`, { name })
      : await call('POST', '/bots', { id, name, password })
    if (res.error) return alert('Error: ' + res.error)
    setBotModal({ open: false, editBot: null })
    loadBots()
  }

  async function handleDeleteBot(botId) {
    const bot = bots.find(b => b.id === botId)
    if (!confirm(`¿Eliminar la bot "${bot?.name || botId}"?`)) return
    const res = await call('DELETE', `/bots/${botId}`)
    if (res.error) return alert('Error: ' + res.error)
    loadBots()
  }

  // ── Telegram CRUD ──
  // Pega contra /bot/{botId}/telegram (bot_portal.py / web/app/api/bot/[botId]/telegram),
  // el mismo endpoint que usa el portal de bot -- antes pegaba a /telegram
  // (sin botId en el path), que nunca existió ni en el Python original.
  async function handleSaveTg({ token, botId }) {
    const res = await call('POST', `/bot/${botId}/telegram`, { token })
    if (!res?.ok) return alert('Error: ' + (res?.detail || 'no se pudo agregar'))
    setTgModal({ open: false, botId: null })
    loadBots()
  }

  async function handleDeleteTg(botId, tokenId) {
    if (!confirm(`¿Eliminar el bot de Telegram con token ID ${tokenId}?`)) return
    const res = await call('DELETE', `/bot/${botId}/telegram/${tokenId}`)
    if (!res?.ok) return alert('Error: ' + (res?.detail || 'no se pudo eliminar'))
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
          <button className="btn-ghost btn-sm" onClick={logout} title="Cerrar sesión">Salir</button>
        </div>
      </header>

      <main>

        {/* ── Sección: Monitor ── */}
        <div className="section-block">
          <div className="section-block-header" onClick={() => toggleSection('monitor', monitorCollapsed, setMonitorCollapsed)}>
            <div className="section-block-title">📊 Monitor</div>
            <button
              className="btn-ghost btn-sm"
              onClick={e => { e.stopPropagation(); toggleSection('monitor', monitorCollapsed, setMonitorCollapsed) }}
            >{monitorCollapsed ? '▼ Expandir' : '▲ Colapsar'}</button>
          </div>
          <div style={{ display: monitorCollapsed ? 'none' : 'block' }}>
            <MonitorPanel active={!monitorCollapsed} />
          </div>
        </div>

        {/* ── Links para clientes ── */}
        <div className="card">
          <div className="card-title">Links para bots</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>Alta nueva bot (link en blanco)</div>
              <div className="share-row">
                <input className="share-url" readOnly value={(import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/bot/nueva'} />
                <button className="btn-blue" onClick={() => navigator.clipboard.writeText((import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/bot/nueva')}>Copiar</button>
                <button className="btn-ghost" onClick={() => window.open((import.meta.env.VITE_PUBLIC_URL || window.location.origin) + '/bot/nueva')}>Abrir</button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Sección: Bots ── */}
        <div className="section-block">
          <div className="section-block-header" onClick={() => setCompaniesCollapsed(c => !c)}>
            <div className="section-block-title">🏢 Bots</div>
            <div className="section-block-actions" onClick={e => e.stopPropagation()}>
              <button className="btn-primary btn-sm" onClick={() => setBotModal({ open: true, editBot: null })}>
                + Nueva bot
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
            <div className="empty">No hay bots configuradas. Creá una con el botón de arriba.</div>
          )}

          {bots.map(bot => (
            <BotCard
              key={bot.id}
              mode="admin"
              bot={normalizeBot(bot)}
              onExpand={b => openBotModal({ bot, normalized: b })}
              apiCall={call}
              onRefresh={loadBots}
              onEditBot={b => setBotModal({ open: true, editBot: b })}
              onDeleteBot={botId => handleDeleteBot(botId)}
              onAddTelegram={botId => setTgModal({ open: true, botId })}
              onDeleteTelegram={conn => handleDeleteTg(bot.id, conn.number)}
              onReconnectTg={conn => handleReconnectTg(conn.number)}
              onReconnectWavi={number => setWaviModal({ open: true, session: number })}
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

      <WaviModal
        open={waviModal.open}
        onClose={() => setWaviModal({ open: false, session: null })}
        session={waviModal.session}
      />

      {/* Modal fullscreen de bot expandida */}
      {expandedBot && (
        <div
          className="overlay open"
          onClick={e => e.target === e.currentTarget && openBotModal(null)}
        >
          <div className="modal" style={{ width: '92vw', maxWidth: '1200px', height: '90vh', overflowY: 'auto', padding: 0, paddingTop: 40 }}>
            <button className="modal-close" onClick={() => openBotModal(null)}>✕</button>
            <BotCard
              mode="admin"
              bot={expandedBot.normalized}
              apiCall={call}
              onRefresh={loadBots}
              onEditBot={b => { openBotModal(null); setBotModal({ open: true, editBot: b }) }}
              onDeleteBot={botId => { openBotModal(null); handleDeleteBot(botId) }}
              onAddTelegram={botId => setTgModal({ open: true, botId })}
              onDeleteTelegram={conn => handleDeleteTg(expandedBot.bot.id, conn.number)}
              onReconnectTg={conn => handleReconnectTg(conn.number)}
              onReconnectWavi={number => setWaviModal({ open: true, session: number })}
            />
          </div>
        </div>
      )}

    </>
  )
}
