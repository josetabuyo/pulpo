import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import StatusBadge from '../components/StatusBadge.jsx'
import ChatWidget from '../components/ChatWidget.jsx'
import { ConexionRow } from './NuevaEmpresaPage.jsx'
import { authFetch, setAccessToken, clearAccessToken, getAccessToken } from '../lib/auth.js'

// ─── Helpers de API empresa ──────────────────────────────────────

async function empresaApi(method, path, body) {
  const res = await authFetch('/api' + path, {
    method,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) return { _unauthorized: true }
  return res.json()
}

async function connectAndPollEmpresa({ botId, number, onQR, onReady, onError }) {
  let interval = null
  const stop = () => { if (interval) { clearInterval(interval); interval = null } }

  let res
  try {
    res = await empresaApi('POST', `/empresa/${botId}/connect/${number}`, null)
  } catch {
    onError('Error de red.')
    return stop
  }

  if (res.error) { onError(res.error); return stop }
  if (res.status === 'ready') { onReady(); return stop }

  const sessionId = res.sessionId

  interval = setInterval(async () => {
    try {
      const data = await empresaApi('GET', `/empresa/${botId}/qr/${sessionId}`, null)
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

function ContactChat({ botId, number, contact, onClose }) {
  const [messages, setMessages] = useState([])

  const load = useCallback(async () => {
    const res = await empresaApi('GET', `/empresa/${botId}/chat/${number}/${contact.phone}`, null).catch(() => null)
    if (Array.isArray(res)) {
      setMessages(res.map(m => ({
        id: m.id,
        body: m.body,
        outbound: m.outbound,
        from: m.outbound ? null : (m.name || m.phone),
        time: m.timestamp?.slice(11, 16),
      })))
    }
  }, [botId, number, contact.phone])

  useEffect(() => {
    load()
    const iv = setInterval(load, 4000)
    return () => clearInterval(iv)
  }, [load])

  async function handleSend(text) {
    const res = await empresaApi('POST', `/empresa/${botId}/chat/${number}/${contact.phone}`, { text }).catch(() => null)
    if (res?.ok) load()
  }

  return (
    <ChatWidget
      title={contact.name || contact.phone}
      subtitle={contact.phone}
      messages={messages}
      onSend={handleSend}
      defaultOpen={true}
      unreadCount={0}
    />
  )
}

// ─── ConexionCard ────────────────────────────────────────────────

function ConexionCard({ conn, botId, onRefresh }) {
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
    const res = await empresaApi('GET', `/empresa/${botId}/messages/${conn.id}`, null).catch(() => null)
    if (Array.isArray(res)) setConvs(res)
  }, [botId, conn.id])

  useEffect(() => {
    loadConvs()
    const iv = setInterval(loadConvs, 5000)
    return () => { clearInterval(iv); stopRef.current?.() }
  }, [loadConvs])

  async function handleConnect() {
    setShowQr(true); setQrSrc(null); setQrStatus('Generando código QR...')
    stopRef.current = await connectAndPollEmpresa({
      botId, number: conn.id,
      onQR(dataUrl) { setQrSrc(dataUrl); setQrStatus('El código se renueva cada 20 segundos') },
      onReady() { stopRef.current = null; setShowQr(false); onRefresh() },
      onError() { stopRef.current = null; setShowQr(false); onRefresh() },
    })
  }

  function handleCancelQr() { stopRef.current?.(); stopRef.current = null; setShowQr(false) }

  async function handleDisconnect() {
    await empresaApi('POST', `/empresa/${botId}/disconnect/${conn.id}`, null).catch(() => null)
    onRefresh()
  }

  return (
    <div className={`conexion-card conexion-card--${isTelegram ? 'tg' : 'wa'}`}>

      {/* Header: icono + número/id + status badge + botones de acción */}
      <div className="conexion-header">
        <span className="conexion-icon">{isTelegram ? '✈️' : '📱'}</span>
        <span className="conexion-number">{isTelegram ? conn.number : `+${conn.number}`}</span>
        <StatusBadge status={conn.status} />
        <div className="conexion-actions">
          {!isTelegram && !showQr && (
            <>
              {isConnected && (
                <button className="btn-danger btn-sm" onClick={handleDisconnect}>Desconectar</button>
              )}
              {!isConnected && !isConnecting && (
                <button className="btn-primary btn-sm" onClick={handleConnect}>Conectar</button>
              )}
              {isConnecting && <span className="portal-connecting-hint">Conectando...</span>}
            </>
          )}
        </div>
      </div>

      {/* QR WhatsApp */}
      {!isTelegram && showQr && (
        <div className="conexion-qr">
          <p className="qr-hint">Abrí WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong></p>
          <div className="qr-wrap">{qrSrc ? <img src={qrSrc} alt="QR" /> : <div className="spinner" />}</div>
          <p className="qr-status">{qrStatus}</p>
          <button className="btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={handleCancelQr}>Cancelar</button>
        </div>
      )}

      {/* Conversaciones: lista inline con expansión */}
      {!showQr && (
        <div className="conv-inline">
          {conversations.length === 0
            ? <div className="empty">Sin mensajes aún</div>
            : [...conversations]
                .sort((a, b) => {
                  if (activeContact?.phone === a.phone) return -1
                  if (activeContact?.phone === b.phone) return 1
                  return (b.timestamp || '').localeCompare(a.timestamp || '')
                })
                .map(m => (
                  <div key={m.phone}>
                    <button
                      className={`conv-row${activeContact?.phone === m.phone ? ' conv-row--active' : ''}`}
                      onClick={() => setContact(c => c?.phone === m.phone ? null : { phone: m.phone, name: m.name })}
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
                    {activeContact?.phone === m.phone && (
                      <div className="conv-inline-chat">
                        <ContactChat
                          botId={botId}
                          number={conn.id}
                         
                          contact={activeContact}
                          onClose={() => setContact(null)}
                        />
                      </div>
                    )}
                  </div>
                ))
          }
        </div>
      )}

    </div>
  )
}

// ─── Vista Configurar ────────────────────────────────────────────

function ConfigView({ botId, botName, onSaved }) {
  const [form, setForm]             = useState({ name: botName, password: '', newPassword: '', autoReplyMessage: '' })
  const [savingData, setSavingData] = useState(false)
  const [dataResult, setDataResult] = useState(null)
  const [waInput, setWaInput]       = useState('')
  const [tgInput, setTgInput]       = useState('')
  const [waError, setWaError]       = useState('')
  const [tgError, setTgError]       = useState('')
  const [conns, setConns]           = useState([])
  const [loadingConn, setLoadingConn] = useState(false)

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const loadConns = useCallback(async () => {
    const res = await empresaApi('GET', `/empresa/${botId}`, null).catch(() => null)
    if (res?.connections) {
      setConns(res.connections)
      setForm(f => ({ ...f, name: res.bot_name, autoReplyMessage: f.autoReplyMessage || res.autoReplyMessage }))
    }
  }, [botId])

  useEffect(() => { loadConns() }, [loadConns])

  async function handleSaveData(e) {
    e.preventDefault(); setSavingData(true); setDataResult(null)
    const body = {}
    if (form.name.trim() && form.name !== botName) body.name = form.name
    if (form.autoReplyMessage.trim()) body.autoReplyMessage = form.autoReplyMessage
    if (form.newPassword) {
      if (form.newPassword !== form.password) { setSavingData(false); setDataResult('pwd-mismatch'); return }
      body.password = form.newPassword
    }
    if (Object.keys(body).length === 0) { setSavingData(false); return }
    const res = await empresaApi('PUT', `/empresa/${botId}/config`, body).catch(() => null)
    setSavingData(false)
    setDataResult(res?.ok ? 'ok' : (res?.detail || 'error'))
    if (res?.ok && body.password) {
      setForm(f => ({ ...f, password: '', newPassword: '' }))
    }
    if (res?.ok) onSaved(form.name || botName)
    setTimeout(() => setDataResult(null), 3000)
  }

  async function addWa(e) {
    e.preventDefault(); setWaError('')
    const number = waInput.trim(); if (!number) return
    setLoadingConn(true)
    const res = await empresaApi('POST', `/empresa/${botId}/whatsapp`, { number }).catch(() => null)
    setLoadingConn(false)
    if (!res?.ok) { setWaError(res?.detail || 'Error al agregar'); return }
    setConns(c => [...c, { id: number, type: 'whatsapp', status: 'stopped' }])
    setWaInput('')
  }

  async function addTg(e) {
    e.preventDefault(); setTgError('')
    const token = tgInput.trim(); if (!token) return
    setLoadingConn(true)
    const res = await empresaApi('POST', `/empresa/${botId}/telegram`, { token }).catch(() => null)
    setLoadingConn(false)
    if (!res?.ok) { setTgError(res?.detail || 'Error al agregar'); return }
    const tokenId = token.split(':')[0]
    const sessionId = `${botId}-tg-${tokenId}`
    setConns(c => [...c, { id: sessionId, type: 'telegram', status: res.requires_restart ? 'stopped' : 'ready' }])
    if (res.requires_restart) setTgError('Agregado. Requiere reinicio del servidor para activarse.')
    setTgInput('')
  }

  async function removeConn(conn) {
    if (!confirm(`¿Eliminar ${conn.type === 'whatsapp' ? '+' + conn.id : conn.id}?`)) return
    if (conn.type === 'whatsapp') {
      await empresaApi('DELETE', `/empresa/${botId}/whatsapp/${conn.id}`, null)
    } else {
      const tokenId = conn.id.split('-tg-')[1]
      await empresaApi('DELETE', `/empresa/${botId}/telegram/${tokenId}`, null)
    }
    setConns(c => c.filter(x => x.id !== conn.id))
  }

  return (
    <main className="portal-main">

      {/* Datos */}
      <div className="card">
        <div className="card-title">Datos de la empresa</div>
        <form onSubmit={handleSaveData}>
          <div className="fg">
            <label>Nombre</label>
            <input value={form.name} onChange={set('name')} placeholder="Nombre de la empresa" />
          </div>
          <div className="fg">
            <label>Mensaje de respuesta automática</label>
            <textarea rows={4} value={form.autoReplyMessage} onChange={set('autoReplyMessage')}
              placeholder="Ej: Hola, te responderemos a la brevedad." />
          </div>
          <div className="fg">
            <label>Nueva contraseña (dejar vacío para no cambiar)</label>
            <input type="password" value={form.newPassword} onChange={set('newPassword')} placeholder="Nueva clave" />
          </div>
          {form.newPassword && (
            <div className="fg">
              <label>Confirmar nueva contraseña</label>
              <input type="password" value={form.password} onChange={set('password')} placeholder="Repetir clave" />
            </div>
          )}
          <div className="portal-save-row">
            <button type="submit" className="btn-primary btn-sm" disabled={savingData}>
              {savingData ? 'Guardando...' : 'Guardar datos'}
            </button>
            {dataResult === 'ok'           && <span className="portal-save-ok">✓ Guardado</span>}
            {dataResult === 'pwd-mismatch' && <span className="portal-save-err">Las contraseñas no coinciden</span>}
            {dataResult && dataResult !== 'ok' && dataResult !== 'pwd-mismatch' && (
              <span className="portal-save-err">{dataResult}</span>
            )}
          </div>
        </form>
      </div>

      {/* Conexiones */}
      <div className="card">
        <div className="card-title">Conexiones</div>

        {/* WhatsApp */}
        <div className="channel-header channel-header--wa">WhatsApp</div>
        <div className="phones-table" style={{ marginBottom: 12 }}>
          {conns.filter(c => c.type === 'whatsapp').map(c => (
            <ConexionRow key={c.id} conn={c} botId={botId}
              onDelete={removeConn}
              onConnected={() => setConns(cs => cs.map(x => x.id === c.id ? { ...x, status: 'ready' } : x))} />
          ))}
          {conns.filter(c => c.type === 'whatsapp').length === 0 && (
            <div className="empty" style={{ padding: 10 }}>Sin números configurados</div>
          )}
        </div>
        <form onSubmit={addWa} style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
          <input style={{ flex: 1 }} type="tel" value={waInput} onChange={e => setWaInput(e.target.value)}
            placeholder="Número sin + (ej: 5491155612767)" />
          <button type="submit" className="btn-primary btn-sm" disabled={loadingConn}>+ Agregar WA</button>
        </form>
        {waError && <div className="error" style={{ fontSize: 13, marginBottom: 8 }}>{waError}</div>}

        {/* Telegram */}
        <div className="channel-header channel-header--tg" style={{ marginTop: 16 }}>Telegram</div>
        <div className="phones-table" style={{ marginBottom: 12 }}>
          {conns.filter(c => c.type === 'telegram').map(c => (
            <ConexionRow key={c.id} conn={c} botId={botId} onDelete={removeConn} />
          ))}
          {conns.filter(c => c.type === 'telegram').length === 0 && (
            <div className="empty" style={{ padding: 10 }}>Sin bots configurados</div>
          )}
        </div>
        <form onSubmit={addTg} style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
          <input style={{ flex: 1 }} value={tgInput} onChange={e => setTgInput(e.target.value)}
            placeholder="Token de @BotFather (123456:ABC...)" />
          <button type="submit" className="btn-primary btn-sm" disabled={loadingConn}>+ Agregar TG</button>
        </form>
        {tgError && <div style={{ fontSize: 13, color: tgError.includes('Requiere') ? '#b45309' : 'var(--error)', marginBottom: 4 }}>{tgError}</div>}
      </div>

    </main>
  )
}

// ─── HerramientasSection ─────────────────────────────────────────

function ToolModal({ botId, tool, contacts, onClose, onSaved }) {
  const isEdit = !!tool
  const [form, setForm] = useState({
    nombre: tool?.nombre ?? '',
    tipo: tool?.tipo ?? 'fixed_message',
    mensaje: tool?.config?.message ?? '',
    conexiones: tool?.connections ?? [],
    incluidos: (tool?.contactos_incluidos ?? []).map(c => c.id),
    excluidos: (tool?.contactos_excluidos ?? []).map(c => c.id),
    incluir_desconocidos: tool?.incluir_desconocidos ?? false,
    exclusiva: tool?.exclusiva ?? false,
  })
  const [allConns, setAllConns] = useState([])
  const [conflicts, setConflicts] = useState([])
  const [validating, setValidating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  // Cargar conexiones disponibles
  useEffect(() => {
    empresaApi('GET', `/empresa/${botId}`, null).catch(() => null).then(res => {
      if (res?.connections) setAllConns(res.connections)
    })
  }, [botId])

  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const setE = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const setCheck = k => e => setForm(f => ({ ...f, [k]: e.target.checked }))

  function toggleConn(id) {
    setForm(f => ({
      ...f,
      conexiones: f.conexiones.includes(id) ? f.conexiones.filter(x => x !== id) : [...f.conexiones, id]
    }))
  }
  function toggleContact(k, id) {
    setForm(f => ({
      ...f,
      [k]: f[k].includes(id) ? f[k].filter(x => x !== id) : [...f[k], id]
    }))
  }

  // Validación en tiempo real
  useEffect(() => {
    if (!form.exclusiva) { setConflicts([]); return }
    const t = setTimeout(async () => {
      setValidating(true)
      const res = await empresaApi('POST', '/tools/validate-exclusivity', {
        empresa_id: botId,
        tool_id: tool?.id ?? null,
        conexiones: form.conexiones,
        contactos_incluidos: form.incluidos,
        incluir_desconocidos: form.incluir_desconocidos,
        exclusiva: form.exclusiva,
      }).catch(() => null)
      setValidating(false)
      setConflicts(res?.conflicts ?? [])
    }, 400)
    return () => clearTimeout(t)
  }, [form.conexiones, form.incluidos, form.incluir_desconocidos, form.exclusiva, botId, tool?.id])

  async function handleSave(e) {
    e.preventDefault(); setErr(''); setSaving(true)
    if (!form.nombre.trim()) { setErr('El nombre es obligatorio'); setSaving(false); return }
    if (conflicts.length > 0) { setErr('Hay conflictos de exclusividad'); setSaving(false); return }

    const payload = {
      nombre: form.nombre.trim(),
      tipo: form.tipo,
      config: { message: form.mensaje },
      conexiones: form.conexiones,
      contactos_incluidos: form.incluidos,
      contactos_excluidos: form.excluidos,
      incluir_desconocidos: form.incluir_desconocidos,
      exclusiva: form.exclusiva,
    }
    const method = isEdit ? 'PUT' : 'POST'
    const path = isEdit ? `/tools/${tool.id}` : `/empresas/${botId}/tools`
    const res = await empresaApi(method, path, payload).catch(() => null)
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

          <div className="fg">
            <label>Nombre</label>
            <input value={form.nombre} onChange={setE('nombre')} placeholder="Ej: Bienvenida VIP" autoFocus />
          </div>

          <div className="fg">
            <label>Tipo</label>
            <select value={form.tipo} onChange={setE('tipo')}>
              <option value="fixed_message">Mensaje fijo</option>
            </select>
          </div>

          {form.tipo === 'fixed_message' && (
            <div className="fg">
              <label>Mensaje</label>
              <textarea rows={3} value={form.mensaje} onChange={setE('mensaje')}
                placeholder="Texto que enviará el bot al activarse" />
            </div>
          )}

          <div className="fg">
            <label>Conexiones</label>
            <div className="tool-checks">
              {allConns.map(c => (
                <label key={c.id} className="tool-check-label">
                  <input type="checkbox" checked={form.conexiones.includes(c.id)}
                    onChange={() => toggleConn(c.id)} />
                  {c.type === 'telegram' ? '✈️' : '📱'} {c.number || c.id}
                </label>
              ))}
              {allConns.length === 0 && <span style={{ fontSize: 12, color: '#999' }}>Sin conexiones configuradas</span>}
            </div>
            <div style={{ fontSize: 11, color: '#999', marginTop: 3 }}>
              Si no seleccionás ninguna, aplica a todas las conexiones de la empresa.
            </div>
          </div>

          <div className="fg">
            <label>Contactos incluidos</label>
            <div className="tool-contact-picks">
              {contacts.map(c => (
                <label key={c.id} className={`tool-pick-item ${form.incluidos.includes(c.id) ? 'tool-pick-item--on' : ''}`}>
                  <input type="checkbox" checked={form.incluidos.includes(c.id)}
                    onChange={() => toggleContact('incluidos', c.id)} />
                  {c.name}
                </label>
              ))}
              {contacts.length === 0 && <span style={{ fontSize: 12, color: '#999' }}>Sin contactos registrados</span>}
            </div>
          </div>

          <div className="fg">
            <label>Contactos excluidos</label>
            <div className="tool-contact-picks">
              {contacts.map(c => (
                <label key={c.id} className={`tool-pick-item ${form.excluidos.includes(c.id) ? 'tool-pick-item--exc' : ''}`}>
                  <input type="checkbox" checked={form.excluidos.includes(c.id)}
                    onChange={() => toggleContact('excluidos', c.id)} />
                  {c.name}
                </label>
              ))}
            </div>
          </div>

          <div className="tool-toggles">
            <label className="tool-toggle">
              <input type="checkbox" checked={form.incluir_desconocidos} onChange={setCheck('incluir_desconocidos')} />
              <div>
                <span>Incluir desconocidos</span>
                <small>Aplica a contactos que no están registrados</small>
              </div>
            </label>
            <label className="tool-toggle">
              <input type="checkbox" checked={form.exclusiva} onChange={setCheck('exclusiva')} />
              <div>
                <span>Exclusiva</span>
                <small>Solo una herramienta exclusiva activa por contacto + conexión</small>
              </div>
            </label>
          </div>

          {conflicts.length > 0 && (
            <div className="conflict-panel">
              <div className="conflict-title">Conflictos de exclusividad {validating ? '(verificando...)' : ''}</div>
              {conflicts.map((c, i) => (
                <div key={i} className="conflict-item">
                  <strong>{c.conflicting_tool_nombre}</strong>
                  {c.conflicting_empresa_id !== botId && ` (${c.conflicting_empresa_nombre})`}
                  {' — '}{c.contact_name ? `contacto: ${c.contact_name}` : 'desconocidos'}
                  {' en '}{c.bot_id}
                </div>
              ))}
            </div>
          )}

          {err && <div className="error" style={{ fontSize: 13, marginBottom: 8 }}>{err}</div>}
          <div className="portal-save-row">
            <button type="button" className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary btn-sm"
              disabled={saving || conflicts.length > 0}>
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function HerramientasSection({ botId }) {
  const [tools, setTools]     = useState([])
  const [contacts, setContacts] = useState([])
  const [modal, setModal]     = useState(null) // null | 'new' | tool-obj

  const load = useCallback(async () => {
    const [t, c] = await Promise.all([
      empresaApi('GET', `/empresas/${botId}/tools`, null).catch(() => []),
      empresaApi('GET', `/bots/${botId}/contacts`, null).catch(() => []),
    ])
    if (Array.isArray(t)) setTools(t)
    if (Array.isArray(c)) setContacts(c)
  }, [botId])

  useEffect(() => { load() }, [load])

  async function handleToggle(tool) {
    await empresaApi('POST', `/tools/${tool.id}/toggle`, null).catch(() => null)
    load()
  }

  async function handleDelete(tool) {
    if (!confirm(`¿Eliminar herramienta "${tool.nombre}"?`)) return
    await empresaApi('DELETE', `/tools/${tool.id}`, null).catch(() => null)
    load()
  }

  function handleSaved() { setModal(null); load() }

  return (
    <div className="card">
      <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Herramientas</span>
        <button className="btn-primary btn-sm" onClick={() => setModal('new')}>+ Nueva</button>
      </div>

      {tools.length === 0
        ? <div className="empty" style={{ marginBottom: 12 }}>Sin herramientas configuradas</div>
        : <table className="contacts-table">
            <thead><tr><th>Nombre</th><th>Tipo</th><th>Estado</th><th>Info</th><th></th></tr></thead>
            <tbody>
              {tools.map(t => (
                <tr key={t.id}>
                  <td>
                    {t.nombre}
                    {t.exclusiva && <span className="ch-badge ch-badge--telegram" style={{ marginLeft: 6 }}>Exclusiva</span>}
                  </td>
                  <td style={{ fontSize: 12, color: '#666' }}>Mensaje fijo</td>
                  <td>
                    <button
                      className={`status-toggle ${t.activa ? 'status-toggle--on' : 'status-toggle--off'}`}
                      onClick={() => handleToggle(t)}
                    >
                      {t.activa ? 'Activa' : 'Inactiva'}
                    </button>
                  </td>
                  <td style={{ fontSize: 12, color: '#888' }}>
                    {t.connections.length > 0 ? t.connections.join(', ') : 'Todas'}
                    {' · '}{t.contactos_incluidos.length > 0
                      ? `${t.contactos_incluidos.length} incluidos`
                      : t.incluir_desconocidos ? 'todos' : '—'}
                  </td>
                  <td>
                    <button className="btn-ghost btn-sm" style={{ marginRight: 4 }} onClick={() => setModal(t)}>Editar</button>
                    <button className="btn-danger btn-sm" onClick={() => handleDelete(t)}>Eliminar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
      }

      {modal && (
        <ToolModal
          botId={botId}
          tool={modal === 'new' ? null : modal}
          contacts={contacts}
          onClose={() => setModal(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}

// ─── ContactosSection ────────────────────────────────────────────

const CHANNEL_LABELS = { whatsapp: '📱 WA', telegram: '✈️ TG' }

function ContactModal({ botId, contact, onClose, onSaved }) {
  const isEdit = !!contact
  const [name, setName]         = useState(contact?.name ?? '')
  const [channels, setChannels] = useState(contact?.channels ?? [])
  const [newType, setNewType]   = useState('whatsapp')
  const [newVal, setNewVal]     = useState('')
  const [chErr, setChErr]       = useState('')
  const [saving, setSaving]     = useState(false)
  const [err, setErr]           = useState('')

  async function handleSave(e) {
    e.preventDefault(); setErr(''); setSaving(true)
    if (!name.trim()) { setErr('El nombre es obligatorio'); setSaving(false); return }

    if (isEdit) {
      const res = await empresaApi('PUT', `/contacts/${contact.id}`, { name }).catch(() => null)
      if (!res?.id) { setErr(res?.detail || 'Error al guardar'); setSaving(false); return }
      onSaved(res)
    } else {
      const res = await empresaApi('POST', `/bots/${botId}/contacts`, { name, channels }).catch(() => null)
      if (!res?.id) { setErr(res?.detail || 'Error al crear'); setSaving(false); return }
      onSaved(res)
    }
    setSaving(false)
  }

  async function addChannel(e) {
    e.preventDefault(); setChErr('')
    const val = newVal.trim(); if (!val) return
    if (isEdit) {
      const res = await empresaApi('POST', `/contacts/${contact.id}/channels`, { type: newType, value: val }).catch(() => null)
      if (!res?.id) { setChErr(res?.detail || 'Error al agregar canal'); return }
      setChannels(c => [...c, res])
    } else {
      setChannels(c => [...c, { id: Date.now(), type: newType, value: val }])
    }
    setNewVal('')
  }

  async function removeChannel(ch) {
    if (isEdit) {
      await empresaApi('DELETE', `/contact-channels/${ch.id}`, null).catch(() => null)
    }
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
          <div className="fg">
            <label>Nombre</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Nombre del contacto" autoFocus />
          </div>

          <div className="fg">
            <label>Canales</label>
            {channels.length > 0
              ? <div className="channel-list">
                  {channels.map(ch => (
                    <div key={ch.id} className="channel-item">
                      <span className="ch-badge ch-badge--small">{CHANNEL_LABELS[ch.type] || ch.type}</span>
                      <span className="ch-value">{ch.value}</span>
                      <button type="button" className="btn-ghost btn-sm" onClick={() => removeChannel(ch)}>✕</button>
                    </div>
                  ))}
                </div>
              : <div className="empty" style={{ marginBottom: 8 }}>Sin canales</div>
            }
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              <select value={newType} onChange={e => setNewType(e.target.value)} style={{ width: 130 }}>
                <option value="whatsapp">WhatsApp</option>
                <option value="telegram">Telegram</option>
              </select>
              <input style={{ flex: 1 }} value={newVal} onChange={e => setNewVal(e.target.value)}
                placeholder={newType === 'whatsapp' ? 'Número (sin +)' : 'Número o @username'} />
              <button type="button" className="btn-ghost btn-sm" onClick={addChannel}>+ Canal</button>
            </div>
            {chErr && <div className="error" style={{ fontSize: 12, marginTop: 4 }}>{chErr}</div>}
          </div>

          {err && <div className="error" style={{ fontSize: 13, marginBottom: 8 }}>{err}</div>}
          <div className="portal-save-row">
            <button type="button" className="btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary btn-sm" disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ContactosSection({ botId }) {
  const [contacts, setContacts]   = useState([])
  const [suggested, setSuggested] = useState([])
  const [modal, setModal]         = useState(null) // null | 'new' | contact-obj
  const [loading, setLoading]     = useState(false)

  const loadContacts = useCallback(async () => {
    const [c, s] = await Promise.all([
      empresaApi('GET', `/bots/${botId}/contacts`, null).catch(() => []),
      empresaApi('GET', `/bots/${botId}/contacts/suggested`, null).catch(() => []),
    ])
    if (Array.isArray(c)) setContacts(c)
    if (Array.isArray(s)) setSuggested(s)
  }, [botId])

  useEffect(() => { loadContacts() }, [loadContacts])

  async function handleDelete(contact) {
    if (!confirm(`¿Eliminar "${contact.name}"?`)) return
    await empresaApi('DELETE', `/contacts/${contact.id}`, null).catch(() => null)
    loadContacts()
  }

  async function handleAddSuggested(s) {
    setLoading(true)
    const res = await empresaApi('POST', `/bots/${botId}/contacts`,
      { name: s.name || s.phone, channels: [{ type: 'whatsapp', value: s.phone }] }
    ).catch(() => null)
    setLoading(false)
    if (res?.id) loadContacts()
  }

  function handleSaved() { setModal(null); loadContacts() }

  return (
    <div className="card">
      <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Contactos</span>
        <button className="btn-primary btn-sm" onClick={() => setModal('new')}>+ Nuevo</button>
      </div>

      {contacts.length === 0
        ? <div className="empty" style={{ marginBottom: 12 }}>Sin contactos registrados</div>
        : <table className="contacts-table">
            <thead><tr><th>Nombre</th><th>Canales</th><th>Creado</th><th></th></tr></thead>
            <tbody>
              {contacts.map(c => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>
                    {c.channels.map(ch => (
                      <span key={ch.id} className={`ch-badge ch-badge--${ch.type}`}>
                        {CHANNEL_LABELS[ch.type]} {ch.value}
                      </span>
                    ))}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{c.created_at?.slice(0, 10)}</td>
                  <td>
                    <button className="btn-ghost btn-sm" style={{ marginRight: 4 }} onClick={() => setModal(c)}>Editar</button>
                    <button className="btn-danger btn-sm" onClick={() => handleDelete(c)}>Eliminar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
      }

      {suggested.length > 0 && (
        <>
          <div className="card-subtitle" style={{ marginTop: 16 }}>Sugeridos (escribieron pero no están registrados)</div>
          <div className="suggested-list">
            {suggested.map(s => (
              <div key={s.phone} className="suggested-item">
                <span>{s.name || s.phone} <small style={{ color: 'var(--text-muted)' }}>({s.phone})</small></span>
                <button className="btn-ghost btn-sm" disabled={loading}
                  onClick={() => handleAddSuggested(s)}>+ Agregar</button>
              </div>
            ))}
          </div>
        </>
      )}

      {modal && (
        <ContactModal
          botId={botId}
          contact={modal === 'new' ? null : modal}
          onClose={() => setModal(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}

// ─── EmpresaDashboard ────────────────────────────────────────────

function EmpresaDashboard({ botId, botName: initialBotName, onLogout }) {
  const [botName, setBotName]       = useState(initialBotName)
  const [data, setData]             = useState(null)
  const [replyMsg, setReplyMsg]     = useState('')
  const [saving, setSaving]         = useState(false)
  const [saveResult, setSaveResult] = useState(null)
  const [waInput, setWaInput]       = useState('')
  const [tgInput, setTgInput]       = useState('')
  const [waError, setWaError]       = useState('')
  const [tgError, setTgError]       = useState('')
  const [loadingConn, setLoadingConn] = useState(false)

  const load = useCallback(async () => {
    const res = await empresaApi('GET', `/empresa/${botId}`, null).catch(() => null)
    if (!res || res.detail) return
    setData(res)
    setBotName(res.bot_name)
    setReplyMsg(prev => prev === '' ? (res.autoReplyMessage ?? '') : prev)
  }, [botId])

  useEffect(() => {
    load()
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [load])

  async function handleSaveTools() {
    setSaving(true); setSaveResult(null)
    const res = await empresaApi('PUT', `/empresa/${botId}/tools`, { autoReplyMessage: replyMsg }).catch(() => null)
    setSaving(false)
    setSaveResult(res?.ok ? 'ok' : 'error')
    if (res?.ok) load()
    setTimeout(() => setSaveResult(null), 3000)
  }

  async function addWa(e) {
    e.preventDefault(); setWaError('')
    const number = waInput.trim(); if (!number) return
    setLoadingConn(true)
    const res = await empresaApi('POST', `/empresa/${botId}/whatsapp`, { number }).catch(() => null)
    setLoadingConn(false)
    if (!res?.ok) { setWaError(res?.detail || 'Error al agregar'); return }
    setWaInput(''); load()
  }

  async function addTg(e) {
    e.preventDefault(); setTgError('')
    const token = tgInput.trim(); if (!token) return
    setLoadingConn(true)
    const res = await empresaApi('POST', `/empresa/${botId}/telegram`, { token }).catch(() => null)
    setLoadingConn(false)
    if (!res?.ok) { setTgError(res?.detail || 'Error al agregar'); return }
    if (res.requires_restart) setTgError('Agregado. Requiere reinicio del servidor para activarse.')
    setTgInput(''); load()
  }

  async function removeConn(conn) {
    if (!confirm(`¿Eliminar ${conn.type === 'whatsapp' ? '+' + conn.id : conn.id}?`)) return
    if (conn.type === 'whatsapp') {
      await empresaApi('DELETE', `/empresa/${botId}/whatsapp/${conn.id}`, null)
    } else {
      const tokenId = conn.id.split('-tg-')[1]
      await empresaApi('DELETE', `/empresa/${botId}/telegram/${tokenId}`, null)
    }
    load()
  }

  const waConns = data?.connections?.filter(c => c.type === 'whatsapp') ?? []
  const tgConns = data?.connections?.filter(c => c.type === 'telegram') ?? []

  return (
    <div className="client-portal">
      <header>
        <span className="portal-title">🐙 {botName}</span>
        <div className="header-actions">
          <button className="btn-ghost btn-sm" onClick={onLogout}>Salir</button>
        </div>
      </header>

      <main className="portal-main">

        {/* 1. RESPUESTA AUTOMÁTICA */}
        <div className="card">
          <div className="card-title">Respuesta automática</div>
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

        {/* 2. WHATSAPP */}
        <div className="card">
          <div className="card-title">📱 WhatsApp</div>
          {waConns.map(conn => (
            <ConexionCard key={conn.id} conn={conn} botId={botId} onRefresh={load}
              onDelete={() => removeConn(conn)} />
          ))}
          {waConns.length === 0 && <div className="empty" style={{ marginBottom: 12 }}>Sin números configurados</div>}
          <form onSubmit={addWa} style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <input style={{ flex: 1 }} type="tel" value={waInput} onChange={e => setWaInput(e.target.value)}
              placeholder="Número sin + (ej: 5491155612767)" />
            <button type="submit" className="btn-primary btn-sm" disabled={loadingConn}>+ Agregar</button>
          </form>
          {waError && <div className="error" style={{ fontSize: 13, marginTop: 6 }}>{waError}</div>}
        </div>

        {/* 3. TELEGRAM */}
        <div className="card">
          <div className="card-title">✈️ Telegram</div>
          {tgConns.map(conn => (
            <ConexionCard key={conn.id} conn={conn} botId={botId} onRefresh={load}
              onDelete={() => removeConn(conn)} />
          ))}
          {tgConns.length === 0 && <div className="empty" style={{ marginBottom: 12 }}>Sin bots configurados</div>}
          <form onSubmit={addTg} style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <input style={{ flex: 1 }} value={tgInput} onChange={e => setTgInput(e.target.value)}
              placeholder="Token de @BotFather (123456:ABC...)" />
            <button type="submit" className="btn-primary btn-sm" disabled={loadingConn}>+ Agregar</button>
          </form>
          {tgError && <div style={{ fontSize: 13, marginTop: 6, color: tgError.includes('Requiere') ? '#b45309' : 'var(--error)' }}>{tgError}</div>}
        </div>

        {/* 4. HERRAMIENTAS */}
        <HerramientasSection botId={botId} />

        {/* 5. CONTACTOS */}
        <ContactosSection botId={botId} />

      </main>
    </div>
  )
}

// ─── EmpresaLogin ────────────────────────────────────────────────

function EmpresaLogin({ onLogin }) {
  const [botId, setBotId] = useState('')
  const [pwd, setPwd]     = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault(); setError('')
    const res = await fetch('/api/empresa/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ bot_id: botId.trim(), password: pwd }),
    }).then(r => r.json()).catch(() => null)

    if (!res?.access_token) { setError('Credenciales incorrectas.'); return }

    setAccessToken(res.access_token)
    localStorage.setItem('empresa_bot_id', res.bot_id)

    // Obtener nombre de la empresa
    const me = await fetch('/api/empresa/me', {
      headers: { 'Authorization': `Bearer ${res.access_token}` },
    }).then(r => r.json()).catch(() => null)

    onLogin({ botId: res.bot_id, botName: me?.nombre ?? res.bot_id })
  }

  return (
    <div className="connect-screen">
      <div className="connect-box">
        <div className="logo">🐙</div>
        <h1>Portal de empresa</h1>
        <p className="subtitle">Ingresá tus credenciales</p>
        <div className="error">{error}</div>
        <form onSubmit={handleSubmit}>
          <input placeholder="ID de empresa (ej: bot_test)" value={botId}
            onChange={e => setBotId(e.target.value)} autoFocus />
          <input type="password" placeholder="Contraseña" value={pwd}
            onChange={e => setPwd(e.target.value)} />
          <button type="submit" className="btn-connect">Entrar</button>
        </form>
        <div className="connect-divider">¿Primera vez?</div>
        <Link to="/empresa/nueva" className="btn-ghost btn-sm" style={{ textAlign: 'center', display: 'block' }}>
          Crear empresa nueva →
        </Link>
      </div>
    </div>
  )
}

// ─── Página principal ────────────────────────────────────────────

export default function EmpresaPage() {
  const [session, setSession] = useState(null)

  useEffect(() => {
    const token = getAccessToken()
    const botId = localStorage.getItem('empresa_bot_id')
    if (!token || !botId) return

    // Verificar que el token sigue siendo válido
    fetch('/api/empresa/me', {
      headers: { 'Authorization': `Bearer ${token}` },
      credentials: 'include',
    }).then(r => {
      if (r.ok) return r.json()
      // Intentar refresh
      return fetch('/api/empresa/refresh', { method: 'POST', credentials: 'include' })
        .then(r2 => {
          if (!r2.ok) throw new Error('refresh failed')
          return r2.json()
        })
        .then(data => {
          setAccessToken(data.access_token)
          return fetch('/api/empresa/me', {
            headers: { 'Authorization': `Bearer ${data.access_token}` },
          }).then(r3 => r3.ok ? r3.json() : null)
        })
    }).then(me => {
      if (me?.bot_id) setSession({ botId: me.bot_id, botName: me.nombre })
      else {
        clearAccessToken()
        localStorage.removeItem('empresa_bot_id')
      }
    }).catch(() => {
      clearAccessToken()
      localStorage.removeItem('empresa_bot_id')
    })
  }, [])

  function handleLogin({ botId, botName }) {
    setSession({ botId, botName })
  }

  async function handleLogout() {
    await fetch('/api/empresa/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
    clearAccessToken()
    localStorage.removeItem('empresa_bot_id')
    setSession(null)
  }

  if (session) {
    return (
      <EmpresaDashboard
        botId={session.botId}
        botName={session.botName}
        onLogout={handleLogout}
      />
    )
  }

  return <EmpresaLogin onLogin={handleLogin} />
}
