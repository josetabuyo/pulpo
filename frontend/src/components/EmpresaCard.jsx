import { useState, useEffect, useRef } from 'react'
import FlowList from './FlowList.jsx'
import UIsList from './UIsList.jsx'

// ─── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  ready: 'Conectado', qr_ready: 'Escaneando', connecting: 'Conectando',
  authenticated: 'Autenticando', disconnected: 'Desconectado',
  failed: 'Error', stopped: 'Sin iniciar', qr_needed: 'Sin iniciar',
}


function isInactive(s) { return ['stopped', 'failed', 'disconnected', undefined, null].includes(s) }

function dotColor(status) {
  if (status === 'ready') return '#2196f3'
  if (['connecting'].includes(status)) return '#f59e0b'
  return '#ef4444'
}

// Normaliza un bot del formato admin (/bots) al formato canónico de EmpresaCard
export function normalizeBot(bot) {
  return {
    id: bot.id,
    name: bot.name,
    connections: (bot.telegram ?? []).map(t => ({
      id: `${bot.id}-tg-${t.tokenId}`, type: 'telegram', number: t.tokenId, status: t.status,
      username: t.username || '', botName: t.botName || '',
    })),
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

// ─── ConnectionRow ──────────────────────────────────────────────────────────────

function ConnectionRow({ conn, mode, simMode, botId, apiCall, onDelete, onReconnect }) {
  const [localStatus, setLocalStatus] = useState(conn.status)
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0, openUp: false })
  const menuRef = useRef(null)
  const menuBtnRef = useRef(null)

  useEffect(() => {
    if (!menuOpen) return
    function onOutside(e) { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [menuOpen])

  function openMenu() {
    const rect = menuBtnRef.current?.getBoundingClientRect()
    if (!rect) { setMenuOpen(true); return }
    const menuHeight = 120
    const spaceBelow = window.innerHeight - rect.bottom
    const openUp = spaceBelow < menuHeight
    setMenuPos({ top: openUp ? rect.top - 4 : rect.bottom + 4, left: rect.right, openUp })
    setMenuOpen(true)
  }

  useEffect(() => setLocalStatus(conn.status), [conn.status])

  const displayId = conn.username ? `@${conn.username}` : conn.botName || conn.number
  const connected = localStatus === 'ready'

  return (
    <div className="ec-conn-row ec-conn-row--tg"
      draggable={mode === 'admin'}
      onDragStart={mode === 'admin' ? e => {
        e.dataTransfer.setData('type', 'telegram')
        e.dataTransfer.setData('sourceBotId', botId)
        e.dataTransfer.setData('tokenId', conn.number)
        e.currentTarget.classList.add('dragging')
      } : undefined}
      onDragEnd={mode === 'admin' ? e => e.currentTarget.classList.remove('dragging') : undefined}
    >
      <div className="ec-conn-main">
        <span className="ec-chan-badge ec-chan-badge--tg">TG</span>
        <span className="ec-conn-id">{displayId}</span>
        {simMode && <span className="ec-sim-badge">SIM</span>}
        <StatusPill status={localStatus} isTg={true} />
        <div className="ec-conn-actions">
          <div style={{ position: 'relative' }}>
            <button
              ref={menuBtnRef}
              className="btn-ghost btn-sm"
              onClick={() => menuOpen ? setMenuOpen(false) : openMenu()}
              title="Opciones"
              style={{ padding: '4px 8px', fontWeight: 600 }}
            >⋯</button>

            {menuOpen && (
              <div ref={menuRef} style={{
                position: 'fixed',
                top: menuPos.openUp ? undefined : menuPos.top,
                bottom: menuPos.openUp ? window.innerHeight - menuPos.top : undefined,
                left: menuPos.left - 180,
                zIndex: 9999,
                background: '#1e293b', border: '1px solid #334155', borderRadius: 6,
                boxShadow: '0 8px 24px rgba(0,0,0,.6)', minWidth: 190, padding: '4px 0',
              }}>
                {mode === 'admin' && connected && (
                  <button className="conn-menu-item conn-menu-item--danger" onClick={() => { setMenuOpen(false) }}>
                    Desconectar
                  </button>
                )}
                {mode === 'admin' && ['stopped', 'failed', 'disconnected'].includes(localStatus) && !simMode && (
                  <button className="conn-menu-item" onClick={() => { onReconnect?.(conn); setMenuOpen(false) }}>
                    Reconectar
                  </button>
                )}
                {mode === 'admin' && (
                  <>
                    <div style={{ margin: '4px 0', borderTop: '1px solid #334155' }} />
                    <button className="conn-menu-item conn-menu-item--danger" onClick={() => { onDelete?.(conn); setMenuOpen(false) }}>
                      🗑 Eliminar conexión
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Google Connections ──────────────────────────────────────────────────────────

const PULPO_EMAIL = 'pulpo-sheets@booming-monitor-459317-d3.iam.gserviceaccount.com'

function GoogleSetupModal({ botId, apiCall, onClose, onSaved }) {
  const [tab, setTab] = useState('pulpo')       // 'pulpo' | 'propia'
  const [jsonText, setJsonText] = useState('')
  const [label, setLabel] = useState('')
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSavePulpo() {
    setSaving(true)
    try {
      const r = await apiCall('POST', `/empresas/${botId}/google-connections`, {
        credentials_json: '__pulpo_default__',
        label: 'Cuenta Pulpo',
      }).catch(() => null)
      // pulpo-default ya existe y es global: no necesita POST, simplemente cerramos
      onSaved?.()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  async function handleSavePropia(e) {
    e.preventDefault()
    setErr('')
    let parsed
    try { parsed = JSON.parse(jsonText) } catch { setErr('JSON inválido'); return }
    if (!parsed.client_email || !parsed.private_key) {
      setErr('El JSON debe tener client_email y private_key')
      return
    }
    setSaving(true)
    const res = await apiCall('POST', `/empresas/${botId}/google-connections`, {
      credentials_json: jsonText,
      label: label || parsed.client_email.split('@')[0],
    }).catch(() => null)
    setSaving(false)
    if (!res?.ok) { setErr(res?.detail || 'Error al guardar'); return }
    onSaved?.()
    onClose()
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <strong>Agregar cuenta Google Sheets</strong>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          <button
            className={tab === 'pulpo' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setTab('pulpo')}
          >Usar cuenta Pulpo</button>
          <button
            className={tab === 'propia' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setTab('propia')}
          >Cuenta propia</button>
        </div>

        {tab === 'pulpo' && (
          <div>
            <p style={{ fontSize: 14, marginBottom: 12, color: '#374151' }}>
              La cuenta de servicio de Pulpo puede escribir en tu hoja.
              Solo necesitás compartirla como <strong>Editor</strong>.
            </p>
            <div style={{ background: '#f1f5f9', borderRadius: 8, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <span style={{ fontSize: 13, fontFamily: 'monospace', flex: 1 }}>{PULPO_EMAIL}</span>
              <button
                className="btn-ghost btn-sm"
                onClick={() => navigator.clipboard.writeText(PULPO_EMAIL)}
              >Copiar</button>
            </div>
            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 20 }}>
              En tu Google Sheet: <strong>Compartir → pegar el email → Editor → Listo</strong>
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
              <button className="btn-primary btn-sm" onClick={handleSavePulpo} disabled={saving}>
                {saving ? 'Guardando...' : 'Confirmar'}
              </button>
            </div>
          </div>
        )}

        {tab === 'propia' && (
          <form onSubmit={handleSavePropia}>
            <div style={{ fontSize: 13, color: '#374151', marginBottom: 12 }}>
              <strong>Pasos para obtener el JSON:</strong>
              <ol style={{ paddingLeft: 18, marginTop: 6, lineHeight: 1.8 }}>
                <li>console.cloud.google.com → Biblioteca → <em>Google Sheets API</em> → Habilitar</li>
                <li>Credenciales → + Crear credenciales → <em>Cuenta de servicio</em> → Crear</li>
                <li>Clic en la cuenta → Claves → Agregar clave → JSON → se descarga</li>
                <li>Pegá el contenido acá</li>
              </ol>
            </div>
            <textarea
              rows={6}
              value={jsonText}
              onChange={e => setJsonText(e.target.value)}
              placeholder='{"type": "service_account", "client_email": "...", "private_key": "..."}'
              style={{ width: '100%', fontFamily: 'monospace', fontSize: 12, resize: 'vertical', boxSizing: 'border-box' }}
            />
            <input
              type="text"
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="Nombre amigable (opcional)"
              style={{ width: '100%', marginTop: 8, boxSizing: 'border-box' }}
            />
            {err && <div style={{ color: '#c00', fontSize: 13, marginTop: 6 }}>{err}</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button type="button" className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
              <button type="submit" className="btn-primary btn-sm" disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

function GoogleConnectionsSection({ botId, apiCall, mode, hideAddButton = false }) {
  const [conns, setConns] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    const data = await apiCall('GET', `/empresas/${botId}/google-connections`, null).catch(() => [])
    setConns(Array.isArray(data) ? data : [])
    setLoading(false)
  }

  useEffect(() => { load() }, [botId])

  async function handleDelete(conn) {
    if (!confirm(`¿Eliminar conexión "${conn.label}"?`)) return
    await apiCall('DELETE', `/empresas/${botId}/google-connections/${conn.id}`, null).catch(() => null)
    load()
  }

  if (loading) return null
  // En modo empresa sin google connections: no mostrar nada (el botón está en la sección "Agregar canal")
  if (conns.length === 0 && mode !== 'admin') return null

  return (
    <div>
      <div className="ec-section-label" style={{ background: '#f0fdf4', color: '#15803d' }}>Google Sheets</div>
      {conns.map(conn => (
        <div key={conn.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderBottom: '1px solid #f1f5f9' }}>
          <span style={{ fontSize: 18 }}>📗</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 500, fontSize: 13 }}>{conn.label}</div>
            <div style={{ fontSize: 12, color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{conn.email}</div>
          </div>
          {conn.id === 'pulpo-default' && (
            <span style={{ fontSize: 11, color: '#6b7280', background: '#f1f5f9', borderRadius: 4, padding: '2px 6px' }}>Pulpo</span>
          )}
          {conn.id !== 'pulpo-default' && (
            <button className="btn-danger btn-sm" onClick={() => handleDelete(conn)}>Eliminar</button>
          )}
        </div>
      ))}
      {!hideAddButton && mode === 'admin' && (
        <div className="ec-add-row">
          <button className="btn-sm" style={{ background: '#f0fdf4', color: '#15803d' }} onClick={() => setShowModal(true)}>+ Google Sheets</button>
        </div>
      )}
      {showModal && <GoogleSetupModal botId={botId} apiCall={apiCall} onClose={() => setShowModal(false)} onSaved={load} />}
    </div>
  )
}

// ─── EmpresaCard (componente principal) ────────────────────────────────────────

export default function EmpresaCard({
  mode,         // 'admin' | 'empresa'
  bot,          // { id, name, connections: [{id, type, number, status}] }
  simMode = false,
  apiCall,      // (method, path, body) => Promise — auth-agnostic
  onRefresh,    // callback cuando se produce algún cambio que el padre debe recargar
  onExpand,     // admin only — abre la card en popup fullscreen

  // Admin-only — abren modales en el padre:
  onEditBot, onDeleteBot,
  onAddTelegram,
  onDeleteTelegram, onReconnectTg,

  // Drag & drop (admin only)
  onDragOver, onDragLeave, onDrop,
}) {
  const [activeTab, setActiveTab] = useState('connections')
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)
  const [hasSummarizer, setHasSummarizer] = useState(false)

  useEffect(() => {
    apiCall('GET', `/empresa/${bot.id}/paused`, null)
      .then(r => { if (r?.paused !== undefined) setPaused(r.paused) })
      .catch(() => {})
  }, [bot.id])

  useEffect(() => {
    setHasSummarizer(false)
    apiCall('GET', `/empresas/${bot.id}/flows/has-node/summarize`, null)
      .then(data => { if (data?.found) setHasSummarizer(true) })
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
  const [tgInput, setTgInput] = useState('')
  const [showGoogleModal, setShowGoogleModal] = useState(false)
  const [tgErr, setTgErr] = useState('')
  const [addingConn, setAddingConn] = useState(false)

  const botId = bot.id

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
    if (!confirm(`¿Eliminar ${conn.number}?`)) return
    const tokenId = conn.id.split('-tg-')[1]
    await apiCall('DELETE', `/empresa/${botId}/telegram/${tokenId}`, null).catch(() => null)
    onRefresh?.()
  }

  // Computed
  const conns = bot.connections ?? []
  const tgConns = conns.filter(c => c.type === 'telegram')

  const tabs = [
    { id: 'connections', label: 'Conexiones', count: conns.length },
    ...(hasSummarizer ? [{ id: 'uis', label: 'UIs', count: null }] : []),
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
                  style={{ background: dotColor(c.status) }}
                  title={`TG ${c.number}: ${STATUS_LABELS[c.status] || c.status}`}
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
            {tgConns.length > 0 && (
              <div>
                <div className="ec-section-label ec-section-label--tg">Telegram</div>
                {tgConns.map(conn => (
                  <ConnectionRow
                    key={conn.id} conn={conn} mode={mode} simMode={simMode}
                    botId={botId} apiCall={apiCall}
                    onDelete={mode === 'admin' ? conn => onDeleteTelegram?.(conn) : conn => handleRemoveConn(conn)}
                    onReconnect={conn => onReconnectTg?.(conn)}
                  />
                ))}
              </div>
            )}

            {conns.length === 0 && mode === 'empresa' && (
              <div className="empty" style={{ padding: '20px 0 8px' }}>Sin canales configurados</div>
            )}

            {/* Google Connections */}
            <GoogleConnectionsSection botId={botId} apiCall={apiCall} mode={mode} hideAddButton={mode === 'admin'} />

            {/* Add row */}
            {mode === 'admin' && (
              <div className="ec-add-row">
                <button className="btn-sm" style={{ background: '#e3f2fd', color: '#0d47a1' }} onClick={() => onAddTelegram?.(botId)}>+ Telegram</button>
                <button className="btn-sm" style={{ background: '#f0fdf4', color: '#15803d' }} onClick={() => setShowGoogleModal(true)}>+ Google Sheets</button>
              </div>
            )}

            {mode === 'empresa' && (
              <div className="ec-add-forms">
                <div className="ec-section-label" style={{ background: '#f8fafc', color: '#64748b', borderTop: '1px solid #e8e8f0' }}>Agregar canal</div>
                <div className="ec-add-form-row">
                  <form onSubmit={handleAddTg} style={{ display: 'flex', gap: 8, flex: 1 }}>
                    <input value={tgInput} onChange={e => setTgInput(e.target.value)}
                      placeholder="Token @BotFather (123456:ABC...)" style={{ flex: 1 }} />
                    <button type="submit" className="btn-sm" style={{ background: '#e3f2fd', color: '#0d47a1' }} disabled={addingConn}>+ TG</button>
                  </form>
                  <button
                    type="button"
                    className="btn-sm"
                    style={{ background: '#f0fdf4', color: '#15803d', alignSelf: 'center' }}
                    onClick={() => setShowGoogleModal(true)}
                  >+ Google Sheets</button>
                </div>
                {tgErr && <div style={{ fontSize: 13, color: tgErr.includes('reinicio') ? '#b45309' : '#c00', padding: '4px 20px' }}>{tgErr}</div>}
              </div>
            )}
            {showGoogleModal && (
              <GoogleSetupModal
                botId={botId} apiCall={apiCall}
                onClose={() => setShowGoogleModal(false)}
                onSaved={() => { setShowGoogleModal(false); onRefresh?.() }}
              />
            )}
          </div>
        )}

        {/* ── UIs ── */}
        {activeTab === 'uis' && (
          <UIsList botId={botId} apiCall={apiCall} />
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
