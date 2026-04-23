import { useState, useEffect, useRef } from 'react'
import SimChat from '../SimChat.jsx'
import FlowList from './FlowList.jsx'
import UIsList from './UIsList.jsx'
import ContactFilterEditor, { DEFAULT_FILTER } from './ContactFilterEditor.jsx'

// ─── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  ready: 'Conectado', qr_ready: 'Escaneando', connecting: 'Conectando',
  authenticated: 'Autenticando', disconnected: 'Desconectado',
  failed: 'Error', stopped: 'Sin iniciar', qr_needed: 'Sin iniciar',
}


const CHANNEL_LABELS = { whatsapp: '📱 WA', telegram: '✈️ TG' }
function channelLabel(ch) { return ch.is_group ? '👥 Grupo WA' : (CHANNEL_LABELS[ch.type] || ch.type) }

function isInactive(s) { return ['stopped', 'failed', 'disconnected', 'qr_needed', undefined, null].includes(s) }
function isConnecting(s) { return ['connecting', 'qr_ready', 'authenticated'].includes(s) }

function dotColor(status, isTg) {
  if (status === 'ready') return isTg ? '#2196f3' : '#25d366'
  if (isConnecting(status)) return '#f59e0b'
  return '#ef4444'
}

// Normaliza un bot del formato admin (/bots) al formato canónico de EmpresaCard
export function normalizeBot(bot) {
  return {
    id: bot.id,
    name: bot.name,
    connections: [
      ...(bot.phones ?? []).map(p => ({
        id: p.number, type: 'whatsapp', number: p.number, status: p.status,
      })),
      ...(bot.telegram ?? []).map(t => ({
        id: `${bot.id}-tg-${t.tokenId}`, type: 'telegram', number: t.tokenId, status: t.status,
      })),
    ],
  }
}

// ─── CopyLinkBtn ─────────────────────────────────────────────────────────────────

function CopyLinkBtn({ botId }) {
  const [copied, setCopied] = useState(false)

  function getUrl() {
    const base = import.meta.env.VITE_PUBLIC_URL || window.location.origin
    return `${base}/empresa/${botId}`
  }

  function handleClick(e) {
    e.stopPropagation()
    const url = getUrl()
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <span
      title={copied ? '¡Copiado!' : getUrl()}
      onClick={handleClick}
      style={{
        cursor: 'pointer',
        fontSize: 13,
        color: copied ? '#22c55e' : '#475569',
        transition: 'color 0.2s',
        userSelect: 'none',
        lineHeight: 1,
      }}
    >
      {copied ? '✓' : '🔗'}
    </span>
  )
}

// ─── StatusPill ─────────────────────────────────────────────────────────────────

function StatusPill({ status, isTg }) {
  const cls = isTg && status === 'ready' ? 's-tg-ready' : `s-${status ?? 'stopped'}`
  return (
    <span className={`badge ${cls}`}>
      <span className="dot" />
      {STATUS_LABELS[status] || status || 'Sin iniciar'}
    </span>
  )
}

// ─── Toggle ──────────────────────────────────────────────────────────────────────

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={`ec-toggle ${checked ? 'ec-toggle--on' : 'ec-toggle--off'}`}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
    />
  )
}

// ─── ContactModal ──────────────────────────────────────────────────────────────

function ContactModal({ botId, contact, apiCall, onClose, onSaved }) {
  const isEdit = !!contact
  const [name, setName] = useState(contact?.name ?? '')
  const [channels, setChannels] = useState(contact?.channels ?? [])
  const [newType, setNewType] = useState('whatsapp')
  const [newVal, setNewVal] = useState('')
  const [newIsGroup, setNewIsGroup] = useState(false)
  const [chErr, setChErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  async function handleSave(e) {
    e.preventDefault(); setErr(''); setSaving(true)
    if (!name.trim()) { setErr('El nombre es obligatorio'); setSaving(false); return }
    let res
    if (isEdit) {
      res = await apiCall('PUT', `/contacts/${contact.id}`, { name }).catch(() => null)
      if (!res?.id) { setErr(res?.detail || 'Error al guardar'); setSaving(false); return }
    } else {
      res = await apiCall('POST', `/bots/${botId}/contacts`, { name, channels }).catch(() => null)
      if (!res?.id) { setErr(res?.detail || 'Error al crear'); setSaving(false); return }
    }
    setSaving(false); onSaved(res)
  }

  async function addChannel(e) {
    e.preventDefault(); setChErr('')
    const val = newVal.trim(); if (!val) return
    if (isEdit) {
      const res = await apiCall('POST', `/contacts/${contact.id}/channels`, { type: newType, value: val, is_group: newIsGroup }).catch(() => null)
      if (!res?.id) { setChErr(res?.detail || 'Error al agregar canal'); return }
      setChannels(c => [...c, res])
    } else {
      setChannels(c => [...c, { id: Date.now(), type: newType, value: val, is_group: newIsGroup }])
    }
    setNewVal(''); setNewIsGroup(false)
  }

  async function removeChannel(ch) {
    if (isEdit) await apiCall('DELETE', `/contact-channels/${ch.id}`, null).catch(() => null)
    setChannels(c => c.filter(x => x.id !== ch.id))
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-header">
          <span>{isEdit ? 'Editar contacto' : 'Nuevo contacto'}</span>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSave}>
          <div className="fg"><label>Nombre</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Nombre del contacto" autoFocus />
          </div>
          <div className="fg"><label>Canales</label>
            {channels.length > 0
              ? <div className="channel-list">
                  {channels.map(ch => (
                    <div key={ch.id} className="channel-item">
                      <span className="ch-badge ch-badge--small">{channelLabel(ch)}</span>
                      <span className="ch-value">{ch.value}</span>
                      <button type="button" className="btn-ghost btn-sm" onClick={() => removeChannel(ch)}>✕</button>
                    </div>
                  ))}
                </div>
              : <div className="empty" style={{ padding: '8px 0', fontSize: 13 }}>Sin canales</div>
            }
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              <select value={newType} onChange={e => { setNewType(e.target.value); setNewIsGroup(false) }} style={{ width: 130 }}>
                <option value="whatsapp">WhatsApp</option>
                <option value="telegram">Telegram</option>
              </select>
              <input style={{ flex: 1, minWidth: 120 }} value={newVal} onChange={e => setNewVal(e.target.value)}
                placeholder={newType === 'whatsapp' ? (newIsGroup ? 'Nombre del grupo' : 'Número (sin +)') : 'Número o @username'} />
              <button type="button" className="btn-ghost btn-sm" onClick={addChannel}>+ Canal</button>
            </div>
            {newType === 'whatsapp' && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginTop: 4, cursor: 'pointer' }}>
                <input type="checkbox" checked={newIsGroup} onChange={e => setNewIsGroup(e.target.checked)} />
                👥 Es grupo de WhatsApp
              </label>
            )}
            {chErr && <div style={{ fontSize: 12, color: '#c00', marginTop: 4 }}>{chErr}</div>}
          </div>
          {err && <div style={{ fontSize: 13, color: '#c00', marginBottom: 8 }}>{err}</div>}
          <div className="portal-save-row">
            <button type="button" className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary btn-sm" disabled={saving}>{saving ? 'Guardando...' : 'Guardar'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── EmpresaConfigTab ──────────────────────────────────────────────────────────

function EmpresaConfigTab({ botId, botName, apiCall, onNameChange }) {
  const [form, setForm] = useState({ name: botName, newPassword: '', confirmPassword: '' })
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    apiCall('GET', `/empresa/${botId}`, null).then(r => {
      if (r?.bot_name) setForm(f => ({ ...f, name: r.bot_name }))
    }).catch(() => {})
  }, [botId, apiCall])

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  async function handleSave(e) {
    e.preventDefault(); setSaving(true); setResult(null)
    const body = {}
    if (form.name.trim() && form.name !== botName) body.name = form.name.trim()
    if (form.newPassword) {
      if (form.newPassword !== form.confirmPassword) { setSaving(false); setResult('pwd-mismatch'); return }
      body.password = form.newPassword
    }
    if (Object.keys(body).length === 0) { setSaving(false); return }
    const res = await apiCall('PUT', `/empresa/${botId}/config`, body).catch(() => null)
    setSaving(false)
    setResult(res?.ok ? 'ok' : (res?.detail || 'error'))
    if (res?.ok) {
      if (body.name) onNameChange?.(body.name)
      if (body.password) setForm(f => ({ ...f, newPassword: '', confirmPassword: '' }))
    }
    setTimeout(() => setResult(null), 3000)
  }

  return (
    <div className="ec-config-tab">
      <form onSubmit={handleSave}>
        <div className="fg"><label>Nombre de la empresa</label>
          <input value={form.name} onChange={set('name')} placeholder="Nombre" />
        </div>
        <div className="fg"><label>Nueva contraseña <small style={{ fontWeight: 400, color: '#94a3b8' }}>(dejar vacío para no cambiar)</small></label>
          <input type="password" value={form.newPassword} onChange={set('newPassword')} placeholder="Nueva contraseña" />
        </div>
        {form.newPassword && (
          <div className="fg"><label>Confirmar contraseña</label>
            <input type="password" value={form.confirmPassword} onChange={set('confirmPassword')} placeholder="Repetir contraseña" />
          </div>
        )}
        <div className="portal-save-row">
          <button type="submit" className="btn-primary btn-sm" disabled={saving}>{saving ? 'Guardando...' : 'Guardar cambios'}</button>
          {result === 'ok' && <span className="portal-save-ok">✓ Guardado</span>}
          {result === 'pwd-mismatch' && <span className="portal-save-err">Las contraseñas no coinciden</span>}
          {result && result !== 'ok' && result !== 'pwd-mismatch' && <span className="portal-save-err">{result}</span>}
        </div>
      </form>
    </div>
  )
}

// ─── ConnectionFilterPanel ───────────────────────────────────────────────────────

// ConnectionFilterPanel — panel de filtro de contactos para una conexión.
// Se renderiza como sibling de ec-conn-main (fuera del flex row de botones).
// Usa ContactFilterPicker para tener el mismo look que el editor de flows.
function ConnectionFilterPanel({ number, botId, apiCall, onClose }) {
  const [filter, setFilter]     = useState(DEFAULT_FILTER)
  const [saving, setSaving]     = useState(false)
  const [loaded, setLoaded]     = useState(false)
  const [contacts, setContacts] = useState([])
  const [suggested, setSuggested] = useState([])

  useEffect(() => {
    Promise.all([
      apiCall('GET', `/connections/${number}/filter-config`, null).catch(() => null),
      apiCall('GET', `/bots/${botId}/contacts`, null).catch(() => []),
      apiCall('GET', `/bots/${botId}/contacts/suggested`, null).catch(() => []),
    ]).then(([filterData, contactsData, suggestedData]) => {
      if (filterData) setFilter({ ...DEFAULT_FILTER, ...filterData })
      if (Array.isArray(contactsData)) setContacts(contactsData)
      if (Array.isArray(suggestedData)) setSuggested(suggestedData)
      setLoaded(true)
    })
  }, [])

  async function save() {
    setSaving(true)
    await apiCall('PUT', `/connections/${number}/filter-config`, filter).catch(() => null)
    setSaving(false)
  }

  return (
    <div style={{ padding: '10px 16px 12px', background: '#0d1424', borderTop: '1px solid #1e293b' }}>
      <div style={{ fontWeight: 600, color: '#cbd5e1', marginBottom: 8, fontSize: 11 }}>
        Filtro default — +{number}
      </div>
      {!loaded
        ? <div style={{ color: '#64748b', fontSize: 11 }}>Cargando...</div>
        : <ContactFilterEditor value={filter} onChange={setFilter} contacts={contacts} suggested={suggested} />
      }
      <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
        <button className="btn-primary btn-sm" onClick={save} disabled={saving || !loaded}>
          {saving ? 'Guardando...' : 'Guardar filtro'}
        </button>
        <button className="btn-ghost btn-sm" onClick={onClose}>Cerrar</button>
      </div>
    </div>
  )
}

// ─── ConnectionRow ──────────────────────────────────────────────────────────────

function ConnectionRow({
  conn, mode, simMode, botId, apiCall, adminPwd,
  onQR, onDisconnect, onScreenshot, onMove, onDelete, onReconnect,
}) {
  const [showQr, setShowQr] = useState(false)
  const [qrSrc, setQrSrc] = useState(null)
  const [qrStatus, setQrStatus] = useState('')
  const [localStatus, setLocalStatus] = useState(conn.status)
  const [showFilter, setShowFilter] = useState(false)
  const [purgeLabel, setPurgeLabel] = useState('Purgar')
  const stopRef = useRef(null)

  async function handlePurge() {
    setPurgeLabel('...')
    try {
      const res = await apiCall('POST', `/whatsapp/purge-drafts-session/${conn.number}`, {})
      setPurgeLabel(res?.cleared > 0 ? `${res.cleared} ✓` : 'OK')
    } catch {
      setPurgeLabel('Error')
    }
    setTimeout(() => setPurgeLabel('Purgar'), 3000)
  }

  useEffect(() => setLocalStatus(conn.status), [conn.status])
  useEffect(() => () => stopRef.current?.(), [])

  const isTg = conn.type === 'telegram'
  const displayId = isTg ? conn.number : `+${conn.number}`
  const connected = localStatus === 'ready'
  const inactive = isInactive(localStatus)
  const connecting = isConnecting(localStatus)

  async function empresaConnect() {
    setShowQr(true); setQrSrc(null); setQrStatus('Iniciando...')
    let interval = null
    const stop = () => { if (interval) { clearInterval(interval); interval = null } }
    stopRef.current = stop

    const res = await apiCall('POST', `/empresa/${botId}/connect/${conn.id}`, null).catch(() => null)
    if (!res || res.detail) { stop(); setShowQr(false); return }
    if (res.status === 'ready') { stop(); setLocalStatus('ready'); setShowQr(false); return }

    interval = setInterval(async () => {
      const data = await apiCall('GET', `/empresa/${botId}/qr/${conn.id}`, null).catch(() => null)
      if (!data) return
      if (data.status === 'ready') { stop(); setLocalStatus('ready'); setShowQr(false) }
      else if (['failed', 'disconnected'].includes(data.status)) { stop(); setLocalStatus(data.status); setShowQr(false) }
      else { setLocalStatus(data.status); if (data.qr) { setQrSrc(data.qr); setQrStatus('El código se renueva cada 20 segundos') } }
    }, 3000)
  }

  async function cancelConnect() {
    stopRef.current?.()
    setShowQr(false)
    setLocalStatus('stopped')
    await apiCall('POST', `/empresa/${botId}/disconnect/${conn.id}`, null).catch(() => null)
  }

  async function empresaDisconnect() {
    await apiCall('POST', `/empresa/${botId}/disconnect/${conn.id}`, null).catch(() => null)
    setLocalStatus('disconnected')
  }

  return (
    <div className={`ec-conn-row ec-conn-row--${isTg ? 'tg' : 'wa'}`}
      draggable={mode === 'admin'}
      onDragStart={mode === 'admin' ? e => {
        const type = isTg ? 'telegram' : 'phone'
        e.dataTransfer.setData('type', type)
        e.dataTransfer.setData('sourceBotId', botId)
        if (isTg) e.dataTransfer.setData('tokenId', conn.number)
        else e.dataTransfer.setData('number', conn.number)
        e.currentTarget.classList.add('dragging')
      } : undefined}
      onDragEnd={mode === 'admin' ? e => e.currentTarget.classList.remove('dragging') : undefined}
    >
      <div className="ec-conn-main">
        <span className={`ec-chan-badge ec-chan-badge--${isTg ? 'tg' : 'wa'}`}>{isTg ? 'TG' : 'WA'}</span>
        <span className="ec-conn-id">{displayId}</span>
        {simMode && <span className="ec-sim-badge">SIM</span>}
        <StatusPill status={localStatus} isTg={isTg} />
        <div className="ec-conn-actions">

          {/* ── Admin actions ── */}
          {mode === 'admin' && !isTg && inactive && !simMode && (
            <button className="btn-primary btn-sm" onClick={() => onQR?.(conn)}>Vincular QR</button>
          )}
          {mode === 'admin' && !isTg && inactive && simMode && (
            <button className="btn-primary btn-sm" onClick={() => onQR?.(conn)}>Conectar sim</button>
          )}
          {mode === 'admin' && connected && !isTg && !simMode && (
            <button className="btn-ghost btn-sm" onClick={() => onScreenshot?.(conn)} title="Ver browser headless">👁 Ver</button>
          )}
          {mode === 'admin' && connected && !isTg && !simMode && (
            <button
              className="btn-ghost btn-sm"
              onClick={handlePurge}
              disabled={purgeLabel === '...'}
              title="Eliminar borradores que quedaron en los chats de esta sesión WA"
              style={{ fontSize: 11 }}
            >
              {purgeLabel === 'Purgar' ? '🧹 Purgar' : purgeLabel}
            </button>
          )}
          {mode === 'admin' && connected && (
            <button className="btn-danger btn-sm" onClick={() => onDisconnect?.(conn)}>Desconectar</button>
          )}
          {mode === 'admin' && isTg && ['stopped', 'failed', 'disconnected'].includes(localStatus) && !simMode && (
            <button className="btn-blue btn-sm" onClick={() => onReconnect?.(conn)}>Reconectar</button>
          )}
          {mode === 'admin' && !isTg && (
            <button className="btn-ghost btn-sm" onClick={() => onMove?.(conn)}>Mover</button>
          )}
          {!isTg && (
            <button
              className="btn-ghost btn-sm"
              onClick={() => setShowFilter(f => !f)}
              title="Filtro default de esta conexión"
              style={{ fontSize: 11 }}
            >
              ⚙ Filtro
            </button>
          )}
          {mode === 'admin' && (
            <button className="btn-danger btn-sm" onClick={() => onDelete?.(conn)}>Eliminar</button>
          )}

          {/* ── Empresa actions ── */}
          {mode === 'empresa' && !isTg && !showQr && inactive && !simMode && (
            <button className="btn-primary btn-sm" onClick={empresaConnect}>Conectar</button>
          )}
          {mode === 'empresa' && !isTg && !showQr && inactive && simMode && (
            <button className="btn-primary btn-sm" onClick={() => apiCall('POST', `/sim/connect/${conn.number}`, null).then(() => setLocalStatus('ready'))}>
              Conectar sim
            </button>
          )}
          {mode === 'empresa' && !isTg && !showQr && connected && (
            <button className="btn-danger btn-sm" onClick={empresaDisconnect}>Desconectar</button>
          )}
          {mode === 'empresa' && !isTg && !showQr && connecting && (
            <span className="ec-conn-hint">Conectando...</span>
          )}
        </div>
      </div>

      {/* Filter panel (outside flex, available in both modes) */}
      {showFilter && !isTg && (
        <ConnectionFilterPanel
          number={conn.number}
          botId={botId}
          apiCall={apiCall}
          onClose={() => setShowFilter(false)}
        />
      )}

      {/* QR inline (empresa mode) */}
      {mode === 'empresa' && showQr && (
        <div className="ec-qr-inline">
          <p className="qr-hint">WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong></p>
          <div className="qr-wrap">{qrSrc ? <img src={qrSrc} alt="QR" /> : <div className="spinner" />}</div>
          <p className="qr-status">{qrStatus}</p>
          <button className="btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={cancelConnect}>Cancelar</button>
        </div>
      )}

      {/* SimChat (admin mode + sim + connected WA) */}
      {mode === 'admin' && simMode && connected && !isTg && (
        <SimChat number={conn.number} pwd={adminPwd} />
      )}
    </div>
  )
}

// ─── EmpresaCard (componente principal) ────────────────────────────────────────

export default function EmpresaCard({
  mode,         // 'admin' | 'empresa'
  bot,          // { id, name, connections: [{id, type, number, status}] }
  simMode = false,
  apiCall,      // (method, path, body) => Promise — auth-agnostic
  adminPwd,     // solo para SimChat en modo admin
  onRefresh,    // callback cuando se produce algún cambio que el padre debe recargar
  onExpand,     // admin only — abre la card en popup fullscreen

  // Admin-only — abren modales en el padre:
  onEditBot, onDeleteBot,
  onAddPhone, onAddTelegram,
  onDeletePhone, onMovePhone,
  onDeleteTelegram, onReconnectTg,
  onConnectWA, onDisconnectWA, onScreenshot,

  // Drag & drop (admin only)
  onDragOver, onDragLeave, onDrop,
}) {
  const [activeTab, setActiveTab] = useState('connections')
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)

  useEffect(() => {
    apiCall('GET', `/empresa/${bot.id}/paused`, null)
      .then(r => { if (r?.paused !== undefined) setPaused(r.paused) })
      .catch(() => {})
  }, [bot.id])

  async function togglePause() {
    setPauseLoading(true)
    try {
      const res = await apiCall('PUT', `/empresa/${bot.id}/paused`, { paused: !paused })
      if (res?.ok) setPaused(!paused)
    } finally {
      setPauseLoading(false)
    }
  }

  // Empresa mode: inline add forms for connections
  const [waInput, setWaInput] = useState('')
  const [tgInput, setTgInput] = useState('')
  const [waErr, setWaErr] = useState('')
  const [tgErr, setTgErr] = useState('')
  const [addingConn, setAddingConn] = useState(false)

  const botId = bot.id

  // Empresa mode: agregar conexiones
  async function handleAddWa(e) {
    e.preventDefault(); setWaErr('')
    const number = waInput.trim(); if (!number) return
    setAddingConn(true)
    const res = await apiCall('POST', `/empresa/${botId}/whatsapp`, { number }).catch(() => null)
    setAddingConn(false)
    if (!res?.ok) { setWaErr(res?.detail || 'Error al agregar'); return }
    setWaInput(''); onRefresh?.()
  }

  async function handleAddTg(e) {
    e.preventDefault(); setTgErr('')
    const token = tgInput.trim(); if (!token) return
    setAddingConn(true)
    const res = await apiCall('POST', `/empresa/${botId}/telegram`, { token }).catch(() => null)
    setAddingConn(false)
    if (!res?.ok) { setTgErr(res?.detail || 'Error al agregar'); return }
    if (res.requires_restart) setTgErr('Agregado. Requiere reinicio del servidor para activarse.')
    setTgInput(''); onRefresh?.()
  }

  async function handleRemoveConn(conn) {
    if (!confirm(`¿Eliminar ${conn.type === 'whatsapp' ? '+' + conn.number : conn.number}?`)) return
    if (conn.type === 'whatsapp') {
      await apiCall('DELETE', `/empresa/${botId}/whatsapp/${conn.id}`, null).catch(() => null)
    } else {
      const tokenId = conn.id.split('-tg-')[1]
      await apiCall('DELETE', `/empresa/${botId}/telegram/${tokenId}`, null).catch(() => null)
    }
    onRefresh?.()
  }

  // Computed
  const conns = bot.connections ?? []
  const waConns = conns.filter(c => c.type === 'whatsapp')
  const tgConns = conns.filter(c => c.type === 'telegram')

  const tabs = [
    { id: 'connections', label: 'Conexiones', count: conns.length },
    { id: 'uis', label: 'UIs', count: null },
    { id: 'flow', label: 'Flow', count: null },
    ...(mode === 'empresa' ? [{ id: 'config', label: 'Configurar', count: null }] : []),
  ]

  return (
    <div
      className="ec-card"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {/* ─── Header ─── */}
      <div className="ec-header">
        <div className="ec-header-main">
          <div className="ec-header-info">
            <div className="ec-header-title-row">
              <span className="ec-bot-name">{bot.name}</span>
              <span className="ec-bot-id">{bot.id}</span>
              {simMode && <span className="ec-sim-mode-badge">MODO SIM</span>}
              <CopyLinkBtn botId={bot.id} />
            </div>
          </div>
          <div className="ec-header-right">
            <div className="ec-status-dots">
              {conns.map((c, i) => (
                <span
                  key={i}
                  className="ec-status-dot"
                  style={{ background: dotColor(c.status, c.type === 'telegram') }}
                  title={`${c.type === 'telegram' ? 'TG' : 'WA'} ${c.number}: ${STATUS_LABELS[c.status] || c.status}`}
                />
              ))}
              {conns.length === 0 && <span style={{ fontSize: 11, color: '#94a3b8' }}>Sin canales</span>}
            </div>
            <div className="ec-header-actions">
              {/* Pausa visible en ambos modos */}
              <button
                className="btn-ghost btn-sm"
                onClick={togglePause}
                disabled={pauseLoading}
                title={paused ? 'Bot pausado — click para reanudar' : 'Pausar bot (sin desconectar)'}
                style={paused ? { color: '#f59e0b', borderColor: '#f59e0b' } : {}}
              >
                {pauseLoading ? '...' : paused ? '▶ Reanudar' : '⏸ Pausar'}
              </button>
              {mode === 'admin' && (
                <>
                  <button className="btn-ghost btn-sm" onClick={() => onExpand?.(bot)} title="Expandir">⤢</button>
                  <button className="btn-ghost btn-sm" onClick={() => onEditBot?.(bot)}>Editar</button>
                  <button
                    className="btn-danger btn-sm"
                    onClick={() => onDeleteBot?.(bot.id)}
                    title="Eliminar empresa (pedirá confirmación)"
                    style={{ padding: '4px 7px', fontSize: 14 }}
                  >🗑</button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ─── Tabs ─── */}
      <div className="ec-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`ec-tab ${activeTab === tab.id ? 'ec-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.count != null && <span className="ec-tab-badge">{tab.count}</span>}
          </button>
        ))}
      </div>

      {/* ─── Content ─── */}
      <div className="ec-content">

        {/* ── Connections ── */}
        {activeTab === 'connections' && (
          <div>
            {conns.length === 0 && !mode !== 'empresa' && (
              <div className="empty">Sin canales configurados</div>
            )}

            {waConns.length > 0 && (
              <div>
                <div className="ec-section-label ec-section-label--wa">WhatsApp</div>
                {waConns.map(conn => (
                  <ConnectionRow
                    key={conn.id} conn={conn} mode={mode} simMode={simMode}
                    botId={botId} apiCall={apiCall} adminPwd={adminPwd}
                    onQR={conn => onConnectWA?.(conn)}
                    onDisconnect={conn => onDisconnectWA?.(conn)}
                    onScreenshot={conn => onScreenshot?.(conn)}
                    onMove={conn => onMovePhone?.(conn)}
                    onDelete={mode === 'admin' ? conn => onDeletePhone?.(conn) : conn => handleRemoveConn(conn)}
                    onReconnect={() => {}}
                  />
                ))}
              </div>
            )}

            {tgConns.length > 0 && (
              <div>
                <div className="ec-section-label ec-section-label--tg">Telegram</div>
                {tgConns.map(conn => (
                  <ConnectionRow
                    key={conn.id} conn={conn} mode={mode} simMode={simMode}
                    botId={botId} apiCall={apiCall} adminPwd={adminPwd}
                    onQR={() => {}} onDisconnect={() => {}} onScreenshot={() => {}} onMove={() => {}}
                    onDelete={mode === 'admin' ? conn => onDeleteTelegram?.(conn) : conn => handleRemoveConn(conn)}
                    onReconnect={conn => onReconnectTg?.(conn)}
                  />
                ))}
              </div>
            )}

            {conns.length === 0 && mode === 'empresa' && (
              <div className="empty" style={{ padding: '20px 0 8px' }}>Sin canales configurados</div>
            )}

            {/* Add row */}
            {mode === 'admin' && (
              <div className="ec-add-row">
                <button className="btn-blue btn-sm" onClick={() => onAddPhone?.(botId)}>+ WhatsApp</button>
                <button className="btn-sm" style={{ background: '#e3f2fd', color: '#0d47a1' }} onClick={() => onAddTelegram?.(botId)}>+ Telegram</button>
              </div>
            )}

            {mode === 'empresa' && (
              <div className="ec-add-forms">
                <div className="ec-section-label" style={{ background: '#f8fafc', color: '#64748b', borderTop: '1px solid #e8e8f0' }}>Agregar canal</div>
                <div className="ec-add-form-row">
                  <form onSubmit={handleAddWa} style={{ display: 'flex', gap: 8, flex: 1 }}>
                    <input type="tel" value={waInput} onChange={e => setWaInput(e.target.value)}
                      placeholder="Número WA sin + (ej: 5491155612767)" style={{ flex: 1 }} />
                    <button type="submit" className="btn-primary btn-sm" disabled={addingConn}>+ WA</button>
                  </form>
                  <form onSubmit={handleAddTg} style={{ display: 'flex', gap: 8, flex: 1 }}>
                    <input value={tgInput} onChange={e => setTgInput(e.target.value)}
                      placeholder="Token @BotFather (123456:ABC...)" style={{ flex: 1 }} />
                    <button type="submit" className="btn-sm" style={{ background: '#e3f2fd', color: '#0d47a1' }} disabled={addingConn}>+ TG</button>
                  </form>
                </div>
                {waErr && <div style={{ fontSize: 13, color: '#c00', padding: '4px 20px' }}>{waErr}</div>}
                {tgErr && <div style={{ fontSize: 13, color: tgErr.includes('reinicio') ? '#b45309' : '#c00', padding: '4px 20px' }}>{tgErr}</div>}
              </div>
            )}
          </div>
        )}

        {/* ── UIs ── */}
        {activeTab === 'uis' && (
          <UIsList botId={botId} apiCall={apiCall} waConns={waConns} />
        )}

        {/* ── Flow ── */}
        {activeTab === 'flow' && (
          <FlowList empresaId={botId} apiCall={apiCall} connections={conns} onGoToUIs={() => setActiveTab('uis')} />
        )}

        {/* ── Config (empresa only) ── */}
        {activeTab === 'config' && mode === 'empresa' && (
          <EmpresaConfigTab
            botId={botId}
            botName={bot.name}
            apiCall={apiCall}
            onNameChange={name => onRefresh?.()}
          />
        )}
      </div>

    </div>
  )
}
