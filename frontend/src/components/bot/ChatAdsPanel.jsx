/**
 * Publicidad de un chat puntual + bloque "Integraciones" (bot-key + URLs de
 * webhook). Vive dentro del modal de edición de ChatsTab (ver ChatForm) --
 * solo tiene sentido para un chat ya guardado (necesita `chatId`).
 *
 * Publicar/despublicar reusa exactamente la misma lógica de negocio
 * (cola FILO de 4, lib/business/chat-ads.ts::setAdPublished) que el camino
 * externo por X-Pulpo-Bot-Key -- acá solo dispara el PATCH por sesión.
 */
import { useEffect, useState } from 'react'
import { chatAdsApi } from '../../lib/chatApi.js'

function emptyAdForm() {
  return { title: '', description: '', image_url: '', link_url: '' }
}

function AdFormModal({ ad, onClose, onSaved, onSubmit }) {
  const isNew = !ad
  const [form, setForm] = useState(() => ad ? {
    title: ad.title || '', description: ad.description || '', image_url: ad.image_url || '', link_url: ad.link_url || '',
  } : emptyAdForm())
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  function updateField(key, value) { setForm(f => ({ ...f, [key]: value })) }

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    if (!form.image_url.trim()) { setErr('image_url es requerido'); return }
    setSaving(true)
    const res = await onSubmit(form).catch(() => null)
    setSaving(false)
    if (!res?.id) { setErr(res?.detail || 'Error al guardar'); return }
    onSaved?.(res)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 440 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <strong>{isNew ? 'Nueva publicidad' : 'Editar publicidad'}</strong>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <label style={{ fontSize: 13 }}>
            Imagen (URL) *
            <input type="text" value={form.image_url} onChange={e => updateField('image_url', e.target.value)}
              placeholder="https://..." style={{ width: '100%', marginTop: 4 }} />
          </label>
          {form.image_url && (
            <img src={form.image_url} alt="" style={{ width: '100%', maxHeight: 120, objectFit: 'cover', borderRadius: 8 }} />
          )}
          <label style={{ fontSize: 13 }}>
            Título
            <input type="text" value={form.title} onChange={e => updateField('title', e.target.value)}
              style={{ width: '100%', marginTop: 4 }} />
          </label>
          <label style={{ fontSize: 13 }}>
            Descripción
            <input type="text" value={form.description} onChange={e => updateField('description', e.target.value)}
              style={{ width: '100%', marginTop: 4 }} />
          </label>
          <label style={{ fontSize: 13 }}>
            Link de destino
            <input type="text" value={form.link_url} onChange={e => updateField('link_url', e.target.value)}
              placeholder="https://..." style={{ width: '100%', marginTop: 4 }} />
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button type="submit" className="btn-primary btn-sm" disabled={saving}>
              {saving ? 'Guardando...' : isNew ? 'Crear' : 'Guardar cambios'}
            </button>
            {err && <span style={{ color: 'var(--danger)', fontSize: 13 }}>{err}</span>}
          </div>
        </form>
      </div>
    </div>
  )
}

function AdRow({ ad, onEdit, onDelete, onTogglePublish }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
      border: '1px solid var(--border)', borderRadius: 8, background: 'var(--surface-2)',
    }}>
      <img src={ad.image_url} alt="" style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {ad.title || '(sin título)'}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-subtle)' }}>
          {ad.external_ref ? `externo · ${ad.external_ref}` : 'manual'}
        </div>
      </div>
      <span style={{
        fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 10, flexShrink: 0,
        background: ad.published ? 'var(--success-dim)' : 'var(--surface)',
        color: ad.published ? 'var(--success)' : 'var(--text-subtle)',
      }}>
        {ad.published ? 'Publicada' : 'Sin publicar'}
      </span>
      <button className="btn-sm" onClick={() => onTogglePublish(ad)}>
        {ad.published ? 'Despublicar' : 'Publicar'}
      </button>
      <button className="btn-ghost btn-sm" onClick={() => onEdit(ad)} title="Editar">✎</button>
      <button className="btn-danger btn-sm" onClick={() => onDelete(ad)} title="Eliminar">🗑</button>
    </div>
  )
}

function AdsSection({ botId, chatId, apiCall }) {
  const [ads, setAds] = useState([])
  const [loading, setLoading] = useState(true)
  const [formTarget, setFormTarget] = useState(null) // 'new' | ad | null

  async function load() {
    setLoading(true)
    const data = await chatAdsApi.list(apiCall, botId, chatId).catch(() => [])
    setAds(Array.isArray(data) ? data : [])
    setLoading(false)
  }

  useEffect(() => { load() }, [botId, chatId])

  async function handleTogglePublish(ad) {
    const verb = ad.published ? 'despublicar' : 'publicar'
    if (!confirm(`¿${verb.charAt(0).toUpperCase() + verb.slice(1)} "${ad.title || 'esta publicidad'}"?${!ad.published ? ' Si ya hay 4 publicadas, la más vieja se despublica automáticamente.' : ''}`)) return
    await chatAdsApi.setPublished(apiCall, botId, chatId, ad.id, !ad.published).catch(() => null)
    load()
  }

  async function handleDelete(ad) {
    if (!confirm(`¿Eliminar "${ad.title || 'esta publicidad'}"?`)) return
    await chatAdsApi.remove(apiCall, botId, chatId, ad.id).catch(() => null)
    load()
  }

  const publishedCount = ads.filter(a => a.published).length

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          Publicidad {ads.length > 0 && <span style={{ color: 'var(--text-subtle)', fontWeight: 400 }}>({publishedCount}/4 publicadas)</span>}
        </span>
        <button type="button" className="btn-primary btn-sm" onClick={() => setFormTarget('new')}>+ Agregar</button>
      </div>

      {loading && <div className="empty" style={{ padding: '8px 0' }}>Cargando...</div>}
      {!loading && ads.length === 0 && <div className="empty" style={{ padding: '8px 0' }}>Sin publicidad todavía.</div>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {ads.map(ad => (
          <AdRow key={ad.id} ad={ad} onEdit={setFormTarget} onDelete={handleDelete} onTogglePublish={handleTogglePublish} />
        ))}
      </div>

      {formTarget && (
        <AdFormModal
          ad={formTarget === 'new' ? null : formTarget}
          onClose={() => setFormTarget(null)}
          onSaved={() => { setFormTarget(null); load() }}
          onSubmit={form => formTarget === 'new'
            ? chatAdsApi.create(apiCall, botId, chatId, form)
            : chatAdsApi.update(apiCall, botId, chatId, formTarget.id, form)}
        />
      )}
    </div>
  )
}

function IntegrationsSection({ botId, chatId, apiCall }) {
  const [hasKey, setHasKey] = useState(null)
  const [revealedKey, setRevealedKey] = useState('')
  const [copied, setCopied] = useState('')

  useEffect(() => {
    apiCall('GET', `/bots/${botId}`, null).then(bot => setHasKey(Boolean(bot?.has_api_key))).catch(() => setHasKey(false))
  }, [botId, apiCall])

  async function handleGenerate() {
    if (hasKey && !confirm('¿Regenerar la clave? La anterior deja de funcionar de inmediato.')) return
    const res = await apiCall('POST', `/bots/${botId}/api-key`, {}).catch(() => null)
    if (res?.api_key) { setRevealedKey(res.api_key); setHasKey(true) }
  }

  function copy(label, text) {
    navigator.clipboard.writeText(text).then(() => { setCopied(label); setTimeout(() => setCopied(''), 2000) })
  }

  const publishUrl = `${window.location.origin}/api/chat/${botId}/${chatId}/ads/publish`
  const unpublishUrl = `${window.location.origin}/api/chat/${botId}/${chatId}/ads/unpublish`

  return (
    <details style={{ marginTop: 4 }}>
      <summary style={{ fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Integraciones (automatizar publicidad)</summary>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10, fontSize: 12 }}>
        <p style={{ color: 'var(--text-subtle)', margin: 0 }}>
          Un sistema externo (el CMS del cliente) puede publicar/despublicar publicidad llamando estas rutas
          con el header <code>X-Pulpo-Bot-Key</code>.
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <code style={{ flex: 1, fontSize: 11, padding: '4px 6px', background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {revealedKey || (hasKey ? '••••••••••••••••••••••••' : 'Sin generar todavía')}
          </code>
          {revealedKey && <button type="button" className="btn-sm" onClick={() => copy('key', revealedKey)}>{copied === 'key' ? '✓' : 'Copiar'}</button>}
          <button type="button" className="btn-sm" onClick={handleGenerate}>{hasKey ? 'Regenerar' : 'Generar clave'}</button>
        </div>
        {revealedKey && (
          <p style={{ color: 'var(--danger)', margin: 0 }}>Copiá esta clave ahora -- no se vuelve a mostrar.</p>
        )}

        <label>
          POST publicar (body: external_ref?, title?, description?, image_url, link_url?)
          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
            <code style={{ flex: 1, fontSize: 11, padding: '4px 6px', background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{publishUrl}</code>
            <button type="button" className="btn-sm" onClick={() => copy('publish', publishUrl)}>{copied === 'publish' ? '✓' : 'Copiar'}</button>
          </div>
        </label>
        <label>
          POST despublicar (body: external_ref)
          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
            <code style={{ flex: 1, fontSize: 11, padding: '4px 6px', background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{unpublishUrl}</code>
            <button type="button" className="btn-sm" onClick={() => copy('unpublish', unpublishUrl)}>{copied === 'unpublish' ? '✓' : 'Copiar'}</button>
          </div>
        </label>
      </div>
    </details>
  )
}

export default function ChatAdsPanel({ botId, chatId, apiCall }) {
  if (!chatId) {
    return <div className="empty" style={{ padding: '8px 0', fontSize: 13 }}>Guardá el chat primero para cargar publicidad.</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <AdsSection botId={botId} chatId={chatId} apiCall={apiCall} />
      <IntegrationsSection botId={botId} chatId={chatId} apiCall={apiCall} />
    </div>
  )
}
