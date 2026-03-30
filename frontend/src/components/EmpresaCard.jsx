import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import SimChat from '../SimChat.jsx'

// ─── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  ready: 'Conectado', qr_ready: 'Escaneando', connecting: 'Conectando',
  authenticated: 'Autenticando', disconnected: 'Desconectado',
  failed: 'Error', stopped: 'Sin iniciar', qr_needed: 'Sin iniciar',
}

const TIPO_LABELS = { fixed_message: 'Mensaje fijo', summarizer: 'Sumarizadora', flow: 'Flow (grafo)' }

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

// ─── SummaryModal ─────────────────────────────────────────────────────────────

function SummaryModal({ botId, tool, allContacts, apiCall, adminPwd, onClose }) {
  const [phones, setPhones] = useState(null)
  const [selected, setSelected] = useState(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const defaultFromDate = (() => {
    const d = new Date(); d.setDate(d.getDate() - 30)
    return d.toISOString().split('T')[0]
  })()
  const [fromDate, setFromDate] = useState(defaultFromDate)

  // Mapeo identificador (phone / telegram id) → nombre de contacto
  const phoneToName = useMemo(() => {
    const map = {}
    for (const c of (allContacts || [])) {
      for (const ch of (c.channels || [])) {
        if (ch.type === 'whatsapp' || ch.type === 'telegram') map[ch.value] = c.name
      }
    }
    return map
  }, [allContacts])

  // IDs de contacto de esta herramienta (vacío = todos)
  const toolContactIds = useMemo(() =>
    new Set((tool.contactos_incluidos || []).map(String)),
    [tool]
  )

  // Teléfonos de los contactos de esta herramienta
  const toolPhones = useMemo(() => {
    if (toolContactIds.size === 0) return null // null = sin filtro
    const set = new Set()
    for (const c of (allContacts || [])) {
      if (toolContactIds.has(String(c.id))) {
        for (const ch of (c.channels || [])) {
          if (ch.type === 'whatsapp') set.add(ch.value)
        }
      }
    }
    return set
  }, [allContacts, toolContactIds])

  const loadList = useCallback(() => {
    apiCall('GET', `/summarizer/${botId}`, null)
      .then(r => {
        const all = r?.contacts ?? []
        // Filtrar por contactos de esta herramienta si corresponde
        const filtered = toolPhones ? all.filter(p => toolPhones.has(p)) : all
        setPhones(filtered)
      })
      .catch(() => setPhones([]))
  }, [botId, apiCall, toolPhones])

  useEffect(() => { loadList() }, [loadList])

  async function handleSync() {
    setSyncing(true)
    const body = {}
    if (selected) body.contact_phone = selected
    if (fromDate) body.from_date = fromDate
    await apiCall('POST', `/full-sync`, body).catch(() => null)
    setSyncing(false)
    loadList()
    if (selected) viewContact(selected)
  }

  async function viewContact(phone) {
    setSelected(phone); setLoading(true); setContent('')
    try {
      const headers = {}
      if (adminPwd) {
        headers['x-password'] = adminPwd
      } else {
        const { getAccessToken } = await import('../lib/auth.js')
        const token = getAccessToken()
        if (token) headers['Authorization'] = `Bearer ${token}`
      }
      const r = await fetch(`/api/summarizer/${botId}/${phone}`, { headers })
      setContent(r.ok ? await r.text() : '(sin resumen)')
    } catch { setContent('(error al cargar)') }
    setLoading(false)
  }

  const selectedName = selected ? (phoneToName[selected] || selected) : null

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box" style={{ width: 620 }}>
        <div className="modal-header">
          <span>Resúmenes — {tool.nombre}</span>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        {phones === null
          ? <div className="empty">Cargando...</div>
          : phones.length === 0
            ? <div className="empty" style={{ padding: 20 }}>Sin resúmenes acumulados aún</div>
            : (
              <div style={{ display: 'flex', gap: 12, minHeight: 200 }}>
                <div style={{ width: 160, flexShrink: 0, borderRight: '1px solid #eee', paddingRight: 8 }}>
                  {phones.map(phone => (
                    <button key={phone}
                      className={`btn-ghost btn-sm${selected === phone ? ' ec-btn-active' : ''}`}
                      style={{ display: 'block', width: '100%', textAlign: 'left', marginBottom: 4, lineHeight: 1.3 }}
                      onClick={() => viewContact(phone)}
                    >
                      <span style={{ display: 'block' }}>{phoneToName[phone] || phone}</span>
                      {phoneToName[phone] && <span style={{ display: 'block', fontSize: 10, color: '#aaa' }}>({phone})</span>}
                    </button>
                  ))}
                </div>
                <div style={{ flex: 1, overflow: 'auto', maxHeight: 400 }}>
                  {loading
                    ? <div className="empty">Cargando...</div>
                    : selected
                      ? <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.6 }}>{content}</pre>
                      : <div className="empty" style={{ padding: 16 }}>Seleccioná un contacto</div>
                  }
                </div>
              </div>
            )
        }
        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>Desde:</label>
            <input
              type="date"
              value={fromDate}
              onChange={e => setFromDate(e.target.value)}
              style={{ fontSize: 12, padding: '3px 6px', border: '1px solid #e2e8f0', borderRadius: 6, color: '#1e293b' }}
            />
            <button className="btn-ghost btn-sm" onClick={handleSync} disabled={syncing}>
              {syncing ? '⟳ Sincronizando...' : selected ? `⟳ Re-Sync ${selectedName}` : '⟳ Re-Sync todos'}
            </button>
          </div>
          <button className="btn-ghost btn-sm" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

// ─── ToolForm ──────────────────────────────────────────────────────────────────

function ToolForm({ botId, tool, apiCall, onClose, onSaved }) {
  const isEdit = !!tool
  const [form, setForm] = useState({
    nombre: tool?.nombre ?? '',
    tipo: tool?.tipo ?? 'fixed_message',
    mensaje: tool?.config?.message ?? '',
    todasConexiones: (tool?.connections ?? []).length === 0,
    conexiones: tool?.connections ?? [],
    todosContactos: (tool?.contactos_incluidos ?? []).length === 0 && !!tool,
    incluidos: (tool?.contactos_incluidos ?? []).map(c => c.id),
    excluidos: (tool?.contactos_excluidos ?? []).map(c => c.id),
    incluir_desconocidos: tool?.incluir_desconocidos ?? false,
  })
  const [allConns, setAllConns] = useState([])
  const [contacts, setContacts] = useState([])
  const [conflicts, setConflicts] = useState([])
  const [validating, setValidating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    apiCall('GET', `/empresa/${botId}`, null).then(r => { if (r?.connections) setAllConns(r.connections) }).catch(() => {})
    apiCall('GET', `/bots/${botId}/contacts`, null).then(r => { if (Array.isArray(r)) setContacts(r) }).catch(() => {})
  }, [botId, apiCall])

  useEffect(() => {
    const t = setTimeout(async () => {
      setValidating(true)
      const r = await apiCall('POST', '/tools/validate-exclusivity', {
        empresa_id: botId,
        tool_id: tool?.id ?? null,
        conexiones: form.todasConexiones ? [] : form.conexiones,
        contactos_incluidos: form.todosContactos ? [] : form.incluidos,
        incluir_desconocidos: form.incluir_desconocidos,
        exclusiva: true,
      }).catch(() => null)
      setValidating(false)
      setConflicts(r?.conflicts ?? [])
    }, 400)
    return () => clearTimeout(t)
  }, [form.conexiones, form.incluidos, form.incluir_desconocidos, botId, tool?.id])

  const setE = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  function toggleConn(id) { setForm(f => ({ ...f, conexiones: f.conexiones.includes(id) ? f.conexiones.filter(x => x !== id) : [...f.conexiones, id] })) }
  function toggleContact(k, id) { setForm(f => ({ ...f, [k]: f[k].includes(id) ? f[k].filter(x => x !== id) : [...f[k], id] })) }

  async function handleSave(e) {
    e.preventDefault(); setErr(''); setSaving(true)
    if (!form.nombre.trim()) { setErr('El nombre es obligatorio'); setSaving(false); return }
    if (!form.todasConexiones && form.conexiones.length === 0) { setErr('Seleccioná al menos una conexión'); setSaving(false); return }
    if (!form.todosContactos && !form.incluir_desconocidos && form.incluidos.length === 0) { setErr('Seleccioná al menos un contacto o activá "Incluir desconocidos"'); setSaving(false); return }
    if (conflicts.length > 0) { setErr('Hay conflictos de exclusividad'); setSaving(false); return }
    const payload = {
      nombre: form.nombre.trim(), tipo: form.tipo, config: { message: form.mensaje },
      conexiones: form.todasConexiones ? [] : form.conexiones,
      contactos_incluidos: form.todosContactos ? [] : form.incluidos,
      contactos_excluidos: form.excluidos,
      incluir_desconocidos: form.incluir_desconocidos, exclusiva: true,
    }
    const res = await apiCall(isEdit ? 'PUT' : 'POST', isEdit ? `/tools/${tool.id}` : `/empresas/${botId}/tools`, payload).catch(() => null)
    setSaving(false)
    if (!res?.id) { setErr(res?.detail || 'Error al guardar'); return }
    onSaved(res)
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box" style={{ width: 560 }}>
        <div className="modal-header">
          <span>{isEdit ? 'Editar herramienta' : 'Nueva herramienta'}</span>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSave}>
          <div className="fg"><label>Nombre</label>
            <input value={form.nombre} onChange={setE('nombre')} placeholder="Ej: Bienvenida VIP" autoFocus />
          </div>
          <div className="fg"><label>Tipo</label>
            <select value={form.tipo} onChange={setE('tipo')}>
              <option value="fixed_message">Mensaje fijo</option>
              <option value="summarizer">Sumarizadora (pasiva)</option>
              <option value="flow">Flow (grafo)</option>
            </select>
          </div>
          {form.tipo === 'fixed_message' && (
            <div className="fg"><label>Mensaje</label>
              <textarea rows={3} value={form.mensaje} onChange={setE('mensaje')} placeholder="Texto que enviará el bot al activarse" />
            </div>
          )}
          {form.tipo === 'summarizer' && (
            <div className="fg">
              <div style={{ fontSize: 13, color: '#666', background: '#f5f5f5', padding: '8px 12px', borderRadius: 6 }}>
                Acumula todos los mensajes en un archivo de texto. No envía respuestas automáticas.
              </div>
            </div>
          )}
          {form.tipo === 'flow' && (
            <div className="fg">
              <div style={{ fontSize: 13, color: '#666', background: '#f5f5f5', padding: '8px 12px', borderRadius: 6 }}>
                Ejecuta un grafo LangGraph. La lógica del flow está definida en el backend.
              </div>
            </div>
          )}
          <div className="fg"><label>Conexiones</label>
            <div className="tool-checks">
              <label className="tool-check-label tool-check-label--all">
                <input type="checkbox" checked={form.todasConexiones}
                  onChange={() => setForm(f => ({ ...f, todasConexiones: !f.todasConexiones, conexiones: [] }))} />
                Todas las conexiones
              </label>
              {!form.todasConexiones && allConns.map(c => (
                <label key={c.id} className="tool-check-label">
                  <input type="checkbox" checked={form.conexiones.includes(c.id)} onChange={() => toggleConn(c.id)} />
                  {c.type === 'telegram' ? '✈️' : '📱'} {c.number || c.id}
                </label>
              ))}
            </div>
          </div>
          <div className="fg"><label>Contactos incluidos</label>
            <div className="tool-contact-picks">
              <label className={`tool-pick-item${form.todosContactos ? ' tool-pick-item--on' : ''}`}>
                <input type="checkbox" checked={form.todosContactos}
                  onChange={() => setForm(f => ({ ...f, todosContactos: !f.todosContactos, incluidos: [] }))} />
                Todos los registrados
              </label>
              {!form.todosContactos && contacts.map(c => (
                <label key={c.id} className={`tool-pick-item${form.incluidos.includes(c.id) ? ' tool-pick-item--on' : ''}`}>
                  <input type="checkbox" checked={form.incluidos.includes(c.id)} onChange={() => toggleContact('incluidos', c.id)} />
                  {c.name}
                </label>
              ))}
            </div>
          </div>
          {contacts.length > 0 && (
            <div className="fg"><label>Contactos excluidos <small style={{ fontWeight: 400, color: '#888', marginLeft: 4 }}>— nunca reciben esta herramienta</small></label>
              <div className="tool-contact-picks">
                {contacts.map(c => (
                  <label key={c.id} className={`tool-pick-item${form.excluidos.includes(c.id) ? ' tool-pick-item--exc' : ''}`}>
                    <input type="checkbox" checked={form.excluidos.includes(c.id)} onChange={() => toggleContact('excluidos', c.id)} />
                    {c.name}
                  </label>
                ))}
              </div>
            </div>
          )}
          <div className="tool-toggles">
            <label className="tool-toggle">
              <input type="checkbox" checked={form.incluir_desconocidos} onChange={e => setForm(f => ({ ...f, incluir_desconocidos: e.target.checked }))} />
              <div><span>Incluir desconocidos</span><small>Aplica también a contactos no registrados</small></div>
            </label>
          </div>
          {conflicts.length > 0 && (
            <div className="conflict-panel">
              <div className="conflict-title">Conflictos de exclusividad {validating ? '(verificando...)' : ''}</div>
              {conflicts.map((c, i) => (
                <div key={i} className="conflict-item">
                  <strong>{c.conflicting_tool_nombre}</strong>
                  {c.conflicting_empresa_id !== botId && ` (${c.conflicting_empresa_nombre})`}
                  {' — '}{c.contact_name ? `contacto: ${c.contact_name}` : 'desconocidos'} en {c.bot_id}
                </div>
              ))}
            </div>
          )}
          {err && <div style={{ fontSize: 13, color: '#c00', marginBottom: 8 }}>{err}</div>}
          <div className="portal-save-row">
            <button type="button" className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary btn-sm" disabled={saving || conflicts.length > 0}>
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </div>
    </div>
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

// ─── ConnectionRow ──────────────────────────────────────────────────────────────

function ConnectionRow({
  conn, mode, simMode, botId, apiCall, adminPwd,
  onQR, onDisconnect, onScreenshot, onMove, onDelete, onReconnect,
}) {
  const [showQr, setShowQr] = useState(false)
  const [qrSrc, setQrSrc] = useState(null)
  const [qrStatus, setQrStatus] = useState('')
  const [localStatus, setLocalStatus] = useState(conn.status)
  const stopRef = useRef(null)

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
          {mode === 'admin' && connected && (
            <button className="btn-danger btn-sm" onClick={() => onDisconnect?.(conn)}>Desconectar</button>
          )}
          {mode === 'admin' && isTg && ['stopped', 'failed', 'disconnected'].includes(localStatus) && !simMode && (
            <button className="btn-blue btn-sm" onClick={() => onReconnect?.(conn)}>Reconectar</button>
          )}
          {mode === 'admin' && !isTg && (
            <button className="btn-ghost btn-sm" onClick={() => onMove?.(conn)}>Mover</button>
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

      {/* QR inline (empresa mode) */}
      {mode === 'empresa' && showQr && (
        <div className="ec-qr-inline">
          <p className="qr-hint">WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong></p>
          <div className="qr-wrap">{qrSrc ? <img src={qrSrc} alt="QR" /> : <div className="spinner" />}</div>
          <p className="qr-status">{qrStatus}</p>
          <button className="btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => { stopRef.current?.(); setShowQr(false) }}>Cancelar</button>
        </div>
      )}

      {/* SimChat (admin mode + sim + connected WA) */}
      {mode === 'admin' && simMode && connected && !isTg && (
        <SimChat number={conn.number} pwd={adminPwd} />
      )}
    </div>
  )
}

// ─── ToolRow ───────────────────────────────────────────────────────────────────

function ToolRow({ tool, mode, onToggle, onEdit, onDelete, onViewSummary, toggling }) {
  return (
    <div className={`ec-tool-row ${tool.activa ? 'ec-tool-row--on' : 'ec-tool-row--off'}`}>
      <div className="ec-tool-main">
        <div className="ec-tool-info">
          <span className="ec-tool-name">{tool.nombre}</span>
          <span className="ec-tool-type">{TIPO_LABELS[tool.tipo] ?? tool.tipo}</span>
          <span className="ec-tool-scope">
            {tool.connections?.length > 0 ? tool.connections.join(', ') : 'Todas las conexiones'}
            {' · '}
            {tool.contactos_incluidos?.length > 0
              ? `${tool.contactos_incluidos.length} contacto${tool.contactos_incluidos.length !== 1 ? 's' : ''}`
              : tool.incluir_desconocidos ? 'todos' : '—'}
          </span>
        </div>
        <div className="ec-tool-actions">
          {tool.tipo === 'summarizer' && (
            <button className="btn-ghost btn-sm" onClick={() => onViewSummary(tool)}>Ver resúmenes</button>
          )}
          {mode === 'admin' && (
            <>
              <button className="btn-ghost btn-sm" onClick={() => onEdit(tool)}>Editar</button>
              <button className="btn-danger btn-sm" onClick={() => onDelete(tool)}>Eliminar</button>
            </>
          )}
          {mode === 'admin' && (
            <Toggle checked={tool.activa} onChange={() => onToggle(tool)} disabled={toggling === tool.id} />
          )}
          {mode === 'empresa' && (
            <span className={`ec-tool-status-badge ${tool.activa ? 'ec-tool-status-badge--on' : 'ec-tool-status-badge--off'}`}>
              {tool.activa ? 'Activa' : 'Inactiva'}
            </span>
          )}
        </div>
      </div>
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
  const [tools, setTools] = useState([])
  const [contacts, setContacts] = useState([])
  const [suggested, setSuggested] = useState([])
  const [toolModal, setToolModal] = useState(null)
  const [summaryModal, setSummaryModal] = useState(null)
  const [contactModal, setContactModal] = useState(null)
  const [togglingTool, setTogglingTool] = useState(null)
  const [showSuggested, setShowSuggested] = useState(false)

  // Empresa mode: inline add forms for connections
  const [waInput, setWaInput] = useState('')
  const [tgInput, setTgInput] = useState('')
  const [waErr, setWaErr] = useState('')
  const [tgErr, setTgErr] = useState('')
  const [addingConn, setAddingConn] = useState(false)

  const botId = bot.id

  const loadTools = useCallback(async () => {
    const t = await apiCall('GET', `/empresas/${botId}/tools`, null).catch(() => [])
    if (Array.isArray(t)) setTools(t)
  }, [botId, apiCall])

  const loadContacts = useCallback(async () => {
    const [c, s] = await Promise.all([
      apiCall('GET', `/bots/${botId}/contacts`, null).catch(() => []),
      apiCall('GET', `/bots/${botId}/contacts/suggested`, null).catch(() => []),
    ])
    if (Array.isArray(c)) setContacts(c)
    if (Array.isArray(s)) setSuggested(s)
  }, [botId, apiCall])

  // Cargar herramientas al montar
  useEffect(() => { loadTools() }, [loadTools])

  // Cargar contactos cuando se activa esa pestaña
  useEffect(() => {
    if (activeTab === 'contacts') loadContacts()
  }, [activeTab, loadContacts])

  async function handleToggleTool(tool) {
    setTogglingTool(tool.id)
    await apiCall('POST', `/tools/${tool.id}/toggle`, null).catch(() => null)
    await loadTools()
    setTogglingTool(null)
  }

  async function handleDeleteTool(tool) {
    if (!confirm(`¿Eliminar herramienta "${tool.nombre}"?`)) return
    await apiCall('DELETE', `/tools/${tool.id}`, null).catch(() => null)
    loadTools()
  }

  async function handleDeleteContact(contact) {
    if (!confirm(`¿Eliminar "${contact.name}"?`)) return
    await apiCall('DELETE', `/contacts/${contact.id}`, null).catch(() => null)
    loadContacts()
  }

  async function handleAddSuggested(s) {
    const res = await apiCall('POST', `/bots/${botId}/contacts`, {
      name: s.name || s.phone, channels: [{ type: 'whatsapp', value: s.phone }],
    }).catch(() => null)
    if (res?.id) loadContacts()
  }

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
  const visibleTools = mode === 'empresa' ? tools.filter(t => t.activa) : tools
  const activeToolsCount = tools.filter(t => t.activa).length
  const toolsTabCount = mode === 'admin' ? tools.length : activeToolsCount

  const tabs = [
    { id: 'connections', label: 'Conexiones', count: conns.length },
    { id: 'tools', label: 'Herramientas', count: toolsTabCount },
    { id: 'contacts', label: 'Contactos', count: contacts.length || null },
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
            {mode === 'admin' && (
              <div className="ec-header-actions">
                <button className="btn-ghost btn-sm" onClick={() => onEditBot?.(bot)}>Editar</button>
                <button className="btn-danger btn-sm" onClick={() => onDeleteBot?.(bot.id)}>Eliminar</button>
              </div>
            )}
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

        {/* ── Herramientas ── */}
        {activeTab === 'tools' && (
          <div>
            {visibleTools.length === 0 ? (
              <div className="empty" style={{ padding: '24px 20px' }}>
                {mode === 'admin' ? 'Sin herramientas configuradas para esta empresa.' : 'No hay herramientas habilitadas por el administrador.'}
              </div>
            ) : (
              visibleTools.map(tool => (
                <ToolRow
                  key={tool.id} tool={tool} mode={mode}
                  onToggle={handleToggleTool} onEdit={t => setToolModal(t)}
                  onDelete={handleDeleteTool} onViewSummary={setSummaryModal}
                  toggling={togglingTool}
                />
              ))
            )}
            {mode === 'admin' && (
              <div className="ec-add-row">
                <button className="btn-primary btn-sm" onClick={() => setToolModal('new')}>+ Nueva herramienta</button>
                {tools.length > 0 && (
                  <span className="ec-tools-summary">
                    {activeToolsCount} de {tools.length} activa{tools.length !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Contactos ── */}
        {activeTab === 'contacts' && (
          <div>
            {contacts.length === 0 ? (
              <div className="empty" style={{ padding: '24px 20px' }}>Sin contactos registrados</div>
            ) : (
              <table className="contacts-table" style={{ margin: 0 }}>
                <thead>
                  <tr>
                    <th style={{ paddingLeft: 20 }}>Nombre</th>
                    <th>Canales</th>
                    <th>Alta</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map(c => (
                    <tr key={c.id}>
                      <td style={{ paddingLeft: 20 }}>{c.name}</td>
                      <td>
                        {c.channels.map(ch => (
                          <span key={ch.id} className={`ch-badge ch-badge--${ch.type}`}>{channelLabel(ch)} {ch.value}</span>
                        ))}
                      </td>
                      <td style={{ fontSize: 12, color: '#94a3b8' }}>{c.created_at?.slice(0, 10)}</td>
                      <td style={{ paddingRight: 16 }}>
                        <button className="btn-ghost btn-sm" style={{ marginRight: 4 }} onClick={() => setContactModal(c)}>Editar</button>
                        <button className="btn-danger btn-sm" onClick={() => handleDeleteContact(c)}>Eliminar</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {suggested.length > 0 && (
              <div style={{ padding: '8px 20px 4px' }}>
                <button className="btn-ghost btn-sm" onClick={() => setShowSuggested(s => !s)}>
                  {showSuggested ? '▲' : '▼'} Sugeridos ({suggested.length})
                </button>
                {showSuggested && (
                  <div className="suggested-list" style={{ marginTop: 8 }}>
                    {suggested.map(s => (
                      <div key={s.phone} className="suggested-item">
                        <span>{s.name || s.phone} <small style={{ color: '#94a3b8' }}>({s.phone})</small></span>
                        <button className="btn-ghost btn-sm" onClick={() => handleAddSuggested(s)}>+ Agregar</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="ec-add-row">
              <button className="btn-primary btn-sm" onClick={() => setContactModal('new')}>+ Nuevo contacto</button>
            </div>
          </div>
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

      {/* ─── Modales ─── */}
      {toolModal && (
        <ToolForm
          botId={botId}
          tool={toolModal === 'new' ? null : toolModal}
          apiCall={apiCall}
          onClose={() => setToolModal(null)}
          onSaved={() => { setToolModal(null); loadTools() }}
        />
      )}
      {summaryModal && (
        <SummaryModal
          botId={botId}
          tool={summaryModal}
          allContacts={contacts}
          apiCall={apiCall}
          adminPwd={adminPwd}
          onClose={() => setSummaryModal(null)}
        />
      )}
      {contactModal && (
        <ContactModal
          botId={botId}
          contact={contactModal === 'new' ? null : contactModal}
          apiCall={apiCall}
          onClose={() => setContactModal(null)}
          onSaved={() => { setContactModal(null); loadContacts() }}
        />
      )}
    </div>
  )
}
