/**
 * Tab "Chats" del portal: gestión de PulpoChat (chat web sobre el trigger
 * HTTP) para este bot. Acción de PRO o admin dueño del bot (a diferencia de
 * BotUsersTab, que es admin-only) -- montada en AMBOS modos de BotCard, el
 * backend ya lo garantiza vía proxy.ts::SCOPED_BOT_ROUTES. Mismo estilo que
 * BotUsersTab.jsx (referencia de forma). Ver
 * management/HANDOFF_DASHBOARD_CHATS_VIEW.md §5.1 (gitignoreado) para el
 * diseño completo.
 */
import { useEffect, useState } from 'react'

const TRIGGER_SUFFIX = '_trigger'

function emptyConfig() {
  return {
    flow_id: '', trigger_node_id: '', title: 'PulpoChat',
    is_public: false, enabled: false, banners: [], theme_vars: {}, custom_css: '',
  }
}

export default function ChatsTab({ botId, apiCall }) {
  const [config, setConfig] = useState(null)
  const [flows, setFlows] = useState([])
  const [triggerNodes, setTriggerNodes] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const [ok, setOk] = useState(false)
  const [bannersText, setBannersText] = useState('[]')
  const [themeVarsRows, setThemeVarsRows] = useState([])

  const [access, setAccess] = useState([])
  const [accessInput, setAccessInput] = useState('')

  const [chats, setChats] = useState([])
  const [openChat, setOpenChat] = useState(null) // {id, messages} | null
  const [copied, setCopied] = useState(false)

  const shareUrl = `${window.location.origin}/chat/${botId}`

  async function loadFlows() {
    const data = await apiCall('GET', `/flows/bots/${botId}`, null).catch(() => [])
    setFlows(Array.isArray(data) ? data : [])
  }

  async function loadTriggerNodes(flowId) {
    if (!flowId) { setTriggerNodes([]); return }
    const full = await apiCall('GET', `/flows/bots/${botId}/${flowId}`, null).catch(() => null)
    const nodes = (full?.definition?.nodes ?? []).filter(n => (n.type || '').endsWith(TRIGGER_SUFFIX))
    setTriggerNodes(nodes)
  }

  async function loadConfig() {
    setLoading(true)
    const data = await apiCall('GET', `/bots/${botId}/chat-config`, null).catch(() => null)
    const cfg = data && data.bot_id ? data : emptyConfig()
    setConfig(cfg)
    setBannersText(JSON.stringify(cfg.banners ?? [], null, 2))
    setThemeVarsRows(Object.entries(cfg.theme_vars ?? {}).map(([k, v]) => ({ k, v })))
    if (cfg.flow_id) await loadTriggerNodes(cfg.flow_id)
    setLoading(false)
  }

  async function loadAccess() {
    const data = await apiCall('GET', `/bots/${botId}/chat-access`, null).catch(() => [])
    setAccess(Array.isArray(data) ? data : [])
  }

  async function loadChats() {
    const data = await apiCall('GET', `/bots/${botId}/chats`, null).catch(() => [])
    setChats(Array.isArray(data) ? data : [])
  }

  useEffect(() => { loadFlows(); loadConfig(); loadAccess(); loadChats() }, [botId])

  function updateField(key, value) {
    setConfig(c => ({ ...c, [key]: value }))
  }

  async function handleFlowChange(flowId) {
    updateField('flow_id', flowId)
    updateField('trigger_node_id', '')
    await loadTriggerNodes(flowId)
  }

  function addThemeVar() { setThemeVarsRows(rows => [...rows, { k: '', v: '' }]) }
  function updateThemeVar(i, field, value) {
    setThemeVarsRows(rows => rows.map((r, idx) => idx === i ? { ...r, [field]: value } : r))
  }
  function removeThemeVar(i) { setThemeVarsRows(rows => rows.filter((_, idx) => idx !== i)) }

  async function handleSave() {
    setErr(''); setOk(false)
    let banners
    try {
      banners = bannersText.trim() ? JSON.parse(bannersText) : []
    } catch {
      setErr('Banners: JSON inválido'); return
    }
    if (!config.flow_id) { setErr('Elegí un flow'); return }
    if (!config.trigger_node_id) { setErr('Elegí un nodo trigger'); return }

    const theme_vars = Object.fromEntries(
      themeVarsRows.filter(r => r.k.trim()).map(r => [r.k.trim(), r.v])
    )

    setSaving(true)
    const res = await apiCall('PUT', `/bots/${botId}/chat-config`, {
      flow_id: config.flow_id,
      trigger_node_id: config.trigger_node_id,
      title: config.title,
      is_public: config.is_public,
      enabled: config.enabled,
      banners,
      theme_vars,
      custom_css: config.custom_css || '',
    }).catch(() => null)
    setSaving(false)
    if (!res || res.detail) { setErr(res?.detail || 'Error al guardar'); return }
    setConfig(res)
    setOk(true)
    setTimeout(() => setOk(false), 2000)
  }

  async function handleAddAccess(e) {
    e.preventDefault()
    const email = accessInput.trim().toLowerCase()
    if (!email || !email.includes('@')) return
    const res = await apiCall('POST', `/bots/${botId}/chat-access`, { email }).catch(() => null)
    if (res?.ok) { setAccessInput(''); loadAccess() }
  }

  async function handleRemoveAccess(email) {
    await apiCall('DELETE', `/bots/${botId}/chat-access/${encodeURIComponent(email)}`, null).catch(() => null)
    loadAccess()
  }

  function copyLink() {
    navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  async function openTranscript(chatId) {
    const data = await apiCall('GET', `/bots/${botId}/chats/${chatId}/messages`, null).catch(() => [])
    setOpenChat({ id: chatId, messages: Array.isArray(data) ? data : [] })
  }

  if (loading || !config) return <div className="empty">Cargando...</div>

  return (
    <div className="ec-config-tab">
      <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
        Chat web estilo ChatGPT sobre el trigger HTTP de este bot. Configurá
        el flow que dispara, quién puede entrar, y la marca (banners/CSS).
      </p>

      {/* ── Config ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input type="checkbox" checked={config.enabled} onChange={e => updateField('enabled', e.target.checked)} />
          Habilitado
        </label>

        <label style={{ fontSize: 13 }}>
          Título
          <input
            type="text" value={config.title} onChange={e => updateField('title', e.target.value)}
            placeholder="PulpoChat" style={{ width: '100%', marginTop: 4 }}
          />
        </label>

        <label style={{ fontSize: 13 }}>
          Flow
          <select value={config.flow_id} onChange={e => handleFlowChange(e.target.value)} style={{ width: '100%', marginTop: 4 }}>
            <option value="">-- elegir flow --</option>
            {flows.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>

        <label style={{ fontSize: 13 }}>
          Nodo trigger de entrada
          <select
            value={config.trigger_node_id}
            onChange={e => updateField('trigger_node_id', e.target.value)}
            disabled={!triggerNodes.length}
            style={{ width: '100%', marginTop: 4 }}
          >
            <option value="">-- elegir nodo --</option>
            {triggerNodes.map(n => <option key={n.id} value={n.id}>{n.id} ({n.type})</option>)}
          </select>
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input type="checkbox" checked={config.is_public} onChange={e => updateField('is_public', e.target.checked)} />
          Chat público (sin login)
        </label>

        <label style={{ fontSize: 13 }}>
          Banners (JSON: [{'{'}"img","href","alt"{'}'} | {'{'}"html"{'}'}])
          <textarea
            value={bannersText} onChange={e => setBannersText(e.target.value)}
            rows={4} style={{ width: '100%', marginTop: 4, fontFamily: 'monospace', fontSize: 12 }}
          />
        </label>

        <div style={{ fontSize: 13 }}>
          Variables de tema (overrides de --pc-*)
          {themeVarsRows.map((row, i) => (
            <div key={i} style={{ display: 'flex', gap: 6, marginTop: 4 }}>
              <input placeholder="--pc-accent" value={row.k} onChange={e => updateThemeVar(i, 'k', e.target.value)} style={{ flex: 1 }} />
              <input placeholder="#0ea5e9" value={row.v} onChange={e => updateThemeVar(i, 'v', e.target.value)} style={{ flex: 1 }} />
              <button className="btn-danger btn-sm" onClick={() => removeThemeVar(i)}>✕</button>
            </div>
          ))}
          <button className="btn-sm" style={{ marginTop: 6 }} onClick={addThemeVar}>+ Variable</button>
        </div>

        <label style={{ fontSize: 13 }}>
          CSS avanzado <span style={{ color: '#b45309' }}>(bajo tu responsabilidad)</span>
          <textarea
            value={config.custom_css || ''} onChange={e => updateField('custom_css', e.target.value)}
            rows={3} style={{ width: '100%', marginTop: 4, fontFamily: 'monospace', fontSize: 12 }}
          />
        </label>

        <button className="btn-primary btn-sm" onClick={handleSave} disabled={saving} style={{ alignSelf: 'flex-start' }}>
          {saving ? 'Guardando...' : 'Guardar configuración'}
        </button>
        {err && <div style={{ color: '#c00', fontSize: 13 }}>{err}</div>}
        {ok && <div style={{ color: '#059669', fontSize: 13 }}>✓ Guardado</div>}
      </div>

      {/* ── Link compartible ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, padding: '10px 12px', background: '#f8fafc', borderRadius: 8 }}>
        <code style={{ fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{shareUrl}</code>
        <button className="btn-sm" onClick={copyLink}>{copied ? '✓ Copiado' : 'Copiar link'}</button>
      </div>

      {/* ── Allowlist (solo si no es público) ── */}
      {!config.is_public && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Quién puede chatear</div>
          {access.length === 0 && <div className="empty" style={{ padding: '8px 0' }}>Nadie tiene acceso todavía.</div>}
          {access.map(email => (
            <div key={email} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}>
              <div style={{ flex: 1, fontSize: 13, fontFamily: 'monospace' }}>{email}</div>
              <button className="btn-danger btn-sm" onClick={() => handleRemoveAccess(email)}>Sacar</button>
            </div>
          ))}
          <form onSubmit={handleAddAccess} style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <input type="email" value={accessInput} onChange={e => setAccessInput(e.target.value)} placeholder="nombre@gmail.com" style={{ flex: 1 }} />
            <button type="submit" className="btn-primary btn-sm">+ Dar acceso</button>
          </form>
        </div>
      )}

      {/* ── Listado de conversaciones ── */}
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Conversaciones ({chats.length})</div>
        {chats.length === 0 && <div className="empty" style={{ padding: '8px 0' }}>Sin conversaciones todavía.</div>}
        {chats.map(c => (
          <button
            key={c.id}
            onClick={() => openTranscript(c.id)}
            style={{
              display: 'flex', justifyContent: 'space-between', width: '100%', textAlign: 'left',
              background: 'transparent', color: '#334155', padding: '8px 4px', fontSize: 13,
              borderBottom: '1px solid #f1f5f9', borderRadius: 0,
            }}
          >
            <span>{new Date(c.last_message_at || c.created_at).toLocaleString('es-AR')}</span>
            <span style={{ color: '#94a3b8', fontFamily: 'monospace', fontSize: 11 }}>{c.owner_key}</span>
          </button>
        ))}
      </div>

      {openChat && (
        <div className="modal-overlay" onClick={() => setOpenChat(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span>Transcript</span>
              <button className="btn-ghost btn-sm" onClick={() => setOpenChat(null)}>✕</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '60vh', overflowY: 'auto' }}>
              {openChat.messages.length === 0 && <div className="empty">Sin mensajes.</div>}
              {openChat.messages.map(m => (
                <div key={m.id} style={{ fontSize: 13 }}>
                  <strong style={{ color: m.role === 'user' ? '#a83a5c' : '#7c3aed' }}>{m.role}:</strong>{' '}
                  {m.content}
                  <div style={{ fontSize: 11, color: '#94a3b8' }}>{new Date(m.created_at).toLocaleString('es-AR')}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
