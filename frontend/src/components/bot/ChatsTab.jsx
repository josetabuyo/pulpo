/**
 * Tab "Chats" del portal: gestión de la LISTA de chats (PulpoChat, chat web
 * sobre un nodo trigger de mensaje) de este bot. Acción de PRO o admin
 * dueño del bot (a diferencia de BotUsersTab, que es admin-only) -- montada
 * en AMBOS modos de BotCard, el backend ya lo garantiza vía
 * proxy.ts::SCOPED_BOT_ROUTES.
 *
 * 2026-07-23: un bot puede tener N chats (antes: 1 config por bot). Cada
 * fila tiene su propio link compartible, botón lápiz (editar) y borrar (no
 * afecta las conversaciones ya generadas -- dominio de ejecuciones de
 * flow). Click en la fila (fuera de lápiz/borrar) abre el chat embebido
 * inline, usando el mismo componente que la vista standalone
 * (PulpoChatWidget.jsx).
 */
import { useEffect, useState } from 'react'
import PulpoChatWidget from '../chat/PulpoChatWidget.jsx'

const TRIGGER_SUFFIX = '_trigger'

function emptyForm() {
  return {
    flow_id: '', trigger_node_id: '', title: 'PulpoChat',
    is_public: false, enabled: false, custom_css: '',
  }
}

// ─── Formulario de alta/edición (modal) ────────────────────────────────

function ChatForm({ botId, apiCall, chat, onClose, onSaved }) {
  const isNew = !chat
  const [flows, setFlows] = useState([])
  const [triggerNodes, setTriggerNodes] = useState([])
  const [form, setForm] = useState(() => chat ? {
    flow_id: chat.flow_id, trigger_node_id: chat.trigger_node_id, title: chat.title,
    is_public: chat.is_public, enabled: chat.enabled, custom_css: chat.custom_css || '',
  } : emptyForm())
  const [bannersText, setBannersText] = useState(() => JSON.stringify(chat?.banners ?? [], null, 2))
  const [themeVarsRows, setThemeVarsRows] = useState(() =>
    Object.entries(chat?.theme_vars ?? {}).map(([k, v]) => ({ k, v })))
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    apiCall('GET', `/flows/bots/${botId}`, null).then(d => setFlows(Array.isArray(d) ? d : [])).catch(() => {})
  }, [botId, apiCall])

  useEffect(() => {
    if (!form.flow_id) { setTriggerNodes([]); return }
    let cancelled = false
    apiCall('GET', `/flows/bots/${botId}/${form.flow_id}`, null).then(full => {
      if (cancelled) return
      const nodes = (full?.definition?.nodes ?? []).filter(n => (n.type || '').endsWith(TRIGGER_SUFFIX))
      setTriggerNodes(nodes)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [botId, form.flow_id, apiCall])

  function updateField(key, value) { setForm(f => ({ ...f, [key]: value })) }
  function handleFlowChange(flowId) { setForm(f => ({ ...f, flow_id: flowId, trigger_node_id: '' })) }
  function addThemeVar() { setThemeVarsRows(rows => [...rows, { k: '', v: '' }]) }
  function updateThemeVar(i, field, value) {
    setThemeVarsRows(rows => rows.map((r, idx) => idx === i ? { ...r, [field]: value } : r))
  }
  function removeThemeVar(i) { setThemeVarsRows(rows => rows.filter((_, idx) => idx !== i)) }

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    let banners
    try { banners = bannersText.trim() ? JSON.parse(bannersText) : [] } catch { setErr('Banners: JSON inválido'); return }
    if (!form.flow_id) { setErr('Elegí un flow'); return }
    if (!form.trigger_node_id) { setErr('Elegí un nodo trigger'); return }

    const theme_vars = Object.fromEntries(themeVarsRows.filter(r => r.k.trim()).map(r => [r.k.trim(), r.v]))
    const body = {
      flow_id: form.flow_id, trigger_node_id: form.trigger_node_id, title: form.title,
      is_public: form.is_public, enabled: form.enabled, banners, theme_vars, custom_css: form.custom_css || '',
    }

    setSaving(true)
    const res = isNew
      ? await apiCall('POST', `/bots/${botId}/chat-configs`, body).catch(() => null)
      : await apiCall('PUT', `/bots/${botId}/chat-configs/${chat.id}`, body).catch(() => null)
    setSaving(false)
    if (!res?.id) { setErr(res?.detail || 'Error al guardar'); return }
    onSaved?.(res)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 560, maxHeight: '85vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <strong>{isNew ? 'Nuevo chat' : 'Editar chat'}</strong>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <input type="checkbox" checked={form.enabled} onChange={e => updateField('enabled', e.target.checked)} />
            Habilitado
          </label>

          <label style={{ fontSize: 13 }}>
            Título
            <input type="text" value={form.title} onChange={e => updateField('title', e.target.value)}
              placeholder="PulpoChat" style={{ width: '100%', marginTop: 4 }} />
          </label>

          <label style={{ fontSize: 13 }}>
            Flow
            <select value={form.flow_id} onChange={e => handleFlowChange(e.target.value)} style={{ width: '100%', marginTop: 4 }}>
              <option value="">-- elegir flow --</option>
              {flows.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </label>

          <label style={{ fontSize: 13 }}>
            Nodo trigger de entrada
            <select
              value={form.trigger_node_id}
              onChange={e => updateField('trigger_node_id', e.target.value)}
              disabled={!triggerNodes.length}
              style={{ width: '100%', marginTop: 4 }}
            >
              <option value="">-- elegir nodo --</option>
              {triggerNodes.map(n => <option key={n.id} value={n.id}>{n.id} ({n.type})</option>)}
            </select>
            {form.flow_id && !triggerNodes.length && (
              <small style={{ color: 'var(--text-subtle)' }}>
                Este flow no tiene nodos trigger. Agregá un &quot;Chat Trigger&quot; desde el editor de Flow.
              </small>
            )}
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <input type="checkbox" checked={form.is_public} onChange={e => updateField('is_public', e.target.checked)} />
            Chat público (sin login)
          </label>

          <label style={{ fontSize: 13 }}>
            Banners (JSON: [{'{'}&quot;img&quot;,&quot;href&quot;,&quot;alt&quot;{'}'} | {'{'}&quot;html&quot;{'}'}])
            <textarea value={bannersText} onChange={e => setBannersText(e.target.value)}
              rows={3} style={{ width: '100%', marginTop: 4, fontFamily: 'monospace', fontSize: 12 }} />
          </label>

          <div style={{ fontSize: 13 }}>
            Variables de tema (overrides de --pc-*)
            {themeVarsRows.map((row, i) => (
              <div key={i} style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                <input placeholder="--pc-accent" value={row.k} onChange={e => updateThemeVar(i, 'k', e.target.value)} style={{ flex: 1 }} />
                <input placeholder="#0ea5e9" value={row.v} onChange={e => updateThemeVar(i, 'v', e.target.value)} style={{ flex: 1 }} />
                <button type="button" className="btn-danger btn-sm" onClick={() => removeThemeVar(i)}>✕</button>
              </div>
            ))}
            <button type="button" className="btn-sm" style={{ marginTop: 6 }} onClick={addThemeVar}>+ Variable</button>
          </div>

          <label style={{ fontSize: 13 }}>
            CSS avanzado <span style={{ color: '#b45309' }}>(bajo tu responsabilidad)</span>
            <textarea value={form.custom_css} onChange={e => updateField('custom_css', e.target.value)}
              rows={3} style={{ width: '100%', marginTop: 4, fontFamily: 'monospace', fontSize: 12 }} />
          </label>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button type="submit" className="btn-primary btn-sm" disabled={saving}>
              {saving ? 'Guardando...' : isNew ? 'Crear chat' : 'Guardar cambios'}
            </button>
            {err && <span style={{ color: 'var(--danger)', fontSize: 13 }}>{err}</span>}
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Fila de la lista ───────────────────────────────────────────────────

function ChatRow({ chat, onOpen, onEdit, onDelete }) {
  const [copied, setCopied] = useState(false)
  const shareUrl = `${window.location.origin}/chat/${chat.bot_id}/${chat.id}`

  function copyLink(e) {
    e.stopPropagation()
    navigator.clipboard.writeText(shareUrl).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
  }

  return (
    <div
      onClick={() => onOpen(chat.id)}
      style={{
        display: 'flex', flexDirection: 'column', gap: 6, cursor: 'pointer',
        padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 8,
        background: 'var(--surface-2)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{chat.title}</span>
        <span style={{
          fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 10,
          background: chat.enabled ? 'var(--success-dim)' : 'var(--surface)',
          color: chat.enabled ? 'var(--success)' : 'var(--text-subtle)',
        }}>
          {chat.enabled ? 'Habilitado' : 'Deshabilitado'}
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-subtle)' }}>
          {chat.is_public ? 'Público' : 'Privado'}
        </span>
        <button className="btn-ghost btn-sm" onClick={e => { e.stopPropagation(); onEdit(chat) }} title="Editar">✎</button>
        <button className="btn-danger btn-sm" onClick={e => { e.stopPropagation(); onDelete(chat) }} title="Eliminar">🗑</button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} onClick={e => e.stopPropagation()}>
        <code style={{ fontSize: 11, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-subtle)' }}>
          {shareUrl}
        </code>
        <button className="btn-sm" onClick={copyLink}>{copied ? '✓ Copiado' : 'Copiar link'}</button>
      </div>
    </div>
  )
}

// ─── Tab principal ──────────────────────────────────────────────────────

export default function ChatsTab({ botId, apiCall }) {
  const [chats, setChats] = useState([])
  const [loading, setLoading] = useState(true)
  const [formTarget, setFormTarget] = useState(null) // 'new' | chat object | null
  const [embeddedChatId, setEmbeddedChatId] = useState(null)

  const [access, setAccess] = useState([])
  const [accessInput, setAccessInput] = useState('')

  async function loadChats() {
    setLoading(true)
    const data = await apiCall('GET', `/bots/${botId}/chat-configs`, null).catch(() => [])
    setChats(Array.isArray(data) ? data.map(c => ({ ...c, bot_id: botId })) : [])
    setLoading(false)
  }

  async function loadAccess() {
    const data = await apiCall('GET', `/bots/${botId}/chat-access`, null).catch(() => [])
    setAccess(Array.isArray(data) ? data : [])
  }

  useEffect(() => { loadChats(); loadAccess() }, [botId])

  async function handleDelete(chat) {
    if (!confirm(`¿Eliminar el chat "${chat.title}"? Las conversaciones ya generadas NO se borran.`)) return
    await apiCall('DELETE', `/bots/${botId}/chat-configs/${chat.id}`, null).catch(() => null)
    if (embeddedChatId === chat.id) setEmbeddedChatId(null)
    loadChats()
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

  if (loading) return <div className="empty">Cargando...</div>

  return (
    <div className="ec-config-tab">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: 'var(--text-subtle)' }}>
          {chats.length} chat{chats.length !== 1 ? 's' : ''}
        </span>
        <button className="btn-primary btn-sm" onClick={() => setFormTarget('new')}>+ Agregar chat</button>
      </div>

      {chats.length === 0 && <div className="empty" style={{ padding: '16px 0' }}>Sin chats todavía.</div>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
        {chats.map(chat => (
          <div key={chat.id}>
            <ChatRow
              chat={chat}
              onOpen={id => setEmbeddedChatId(v => v === id ? null : id)}
              onEdit={setFormTarget}
              onDelete={handleDelete}
            />
            {embeddedChatId === chat.id && (
              <div style={{ marginTop: 8 }}>
                <PulpoChatWidget botId={botId} chatId={chat.id} fullscreen={false} />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Allowlist (bot-scoped, aplica a todos los chats privados) ── */}
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
          Quién puede chatear (chats privados)
        </div>
        {access.length === 0 && <div className="empty" style={{ padding: '8px 0' }}>Nadie tiene acceso todavía.</div>}
        {access.map(email => (
          <div key={email} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
            <div style={{ flex: 1, fontSize: 13, fontFamily: 'monospace' }}>{email}</div>
            <button className="btn-danger btn-sm" onClick={() => handleRemoveAccess(email)}>Sacar</button>
          </div>
        ))}
        <form onSubmit={handleAddAccess} style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <input type="email" value={accessInput} onChange={e => setAccessInput(e.target.value)} placeholder="nombre@gmail.com" style={{ flex: 1 }} />
          <button type="submit" className="btn-primary btn-sm">+ Dar acceso</button>
        </form>
      </div>

      {formTarget && (
        <ChatForm
          botId={botId}
          apiCall={apiCall}
          chat={formTarget === 'new' ? null : formTarget}
          onClose={() => setFormTarget(null)}
          onSaved={() => { setFormTarget(null); loadChats() }}
        />
      )}
    </div>
  )
}
