/**
 * ContactsUI — UI de contactos extraída de EmpresaCard.
 *
 * Gestiona su propio estado: contacts, suggested, modal, exclusiones.
 * Props: { botId, apiCall, waConns }
 */
import { useState, useEffect, useCallback } from 'react'

const CHANNEL_LABELS = { whatsapp: '📱 WA', telegram: '✈️ TG' }
function channelLabel(ch) { return ch.is_group ? '👥 Grupo WA' : (CHANNEL_LABELS[ch.type] || ch.type) }

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

// ─── ContactsUI ───────────────────────────────────────────────────────────────

export default function ContactsUI({ botId, apiCall, waConns = [] }) {
  const [contacts, setContacts] = useState([])
  const [suggested, setSuggested] = useState([])
  const [contactModal, setContactModal] = useState(null)
  const [showSuggested, setShowSuggested] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState('')
  const [addingAll, setAddingAll] = useState(false)
  const [excludeState, setExcludeState] = useState(null)

  const loadContacts = useCallback(async () => {
    const [c, s] = await Promise.all([
      apiCall('GET', `/bots/${botId}/contacts`, null).catch(() => []),
      apiCall('GET', `/bots/${botId}/contacts/suggested`, null).catch(() => []),
    ])
    if (Array.isArray(c)) setContacts(c)
    if (Array.isArray(s)) setSuggested(s)
  }, [botId, apiCall])

  useEffect(() => { loadContacts() }, [loadContacts])

  async function handleDeleteContact(contact) {
    if (!confirm(`¿Eliminar "${contact.name}"?`)) return
    await apiCall('DELETE', `/contacts/${contact.id}`, null).catch(() => null)
    loadContacts()
  }

  async function handleImportWA() {
    const activeWA = waConns.filter(c => c.status === 'ready')
    if (!activeWA.length) { setImportMsg('Sin conexiones WA activas'); return }
    setImporting(true)
    setImportMsg('')
    let total = 0
    for (const conn of activeWA) {
      const number = conn.number || conn.id.replace(/\D/g, '')
      const res = await apiCall('POST', `/empresa/${botId}/import-wa-contacts/${number}`, null).catch(() => null)
      if (res?.imported != null) total += res.imported
    }
    setImporting(false)
    setImportMsg(total > 0 ? `${total} nuevos sugeridos importados` : 'Sin contactos nuevos')
    loadContacts()
    setShowSuggested(true)
  }

  async function handleClearSuggested() {
    await apiCall('DELETE', `/empresa/${botId}/suggested-contacts`, null).catch(() => null)
    setSuggested([])
    setShowSuggested(false)
    setImportMsg('Sugeridos limpiados')
  }

  async function handleAddSuggested(s) {
    const name = s.name || s.phone
    const channels = s.phone ? [{ type: 'whatsapp', value: s.phone }] : []
    const res = await apiCall('POST', `/bots/${botId}/contacts`, { name, channels }).catch(() => null)
    if (res?.id) {
      await apiCall('DELETE', `/empresa/${botId}/suggested-contacts/${encodeURIComponent(name)}`, null).catch(() => null)
      setSuggested(prev => prev.filter(x => (x.name || x.phone) !== name))
      loadContacts()
    }
  }

  async function handleExclude(s) {
    const contactKey = s.phone || s.name
    const contactName = s.name || s.phone
    setExcludeState({ contactKey, contactName, flows: null })
    const flowList = await apiCall('GET', `/empresas/${botId}/flows`).catch(() => [])
    const triggerFlows = []
    for (const f of (flowList || [])) {
      const full = await apiCall('GET', `/empresas/${botId}/flows/${f.id}`).catch(() => null)
      if (!full) continue
      const nodes = full.definition?.nodes || []
      if (nodes.some(n => n.type === 'message_trigger')) triggerFlows.push(full)
    }
    if (triggerFlows.length === 0) {
      alert('No hay flows con trigger de mensaje en esta empresa.')
      setExcludeState(null)
      return
    }
    if (triggerFlows.length === 1) {
      await _applyExclusion(triggerFlows[0], contactName)
      setSuggested(prev => prev.filter(x => (x.phone || x.name) !== contactKey))
      setExcludeState(null)
      return
    }
    setExcludeState({ contactKey, contactName, flows: triggerFlows })
  }

  async function _applyExclusion(flow, contactName) {
    const nodes = (flow.definition?.nodes || []).map(n => {
      if (n.type !== 'message_trigger') return n
      const cf = n.config?.contact_filter || { include_all_known: false, include_unknown: false, included: [], excluded: [] }
      const excluded = [...(cf.excluded || [])]
      if (!excluded.includes(contactName)) excluded.push(contactName)
      return { ...n, config: { ...n.config, contact_filter: { ...cf, excluded } } }
    })
    await apiCall('PUT', `/empresas/${botId}/flows/${flow.id}`, { name: flow.name, definition: { ...flow.definition, nodes } })
  }

  async function handleAddAll() {
    if (!suggested.length) return
    setAddingAll(true)
    const toAdd = [...suggested]
    for (const s of toAdd) {
      const name = s.name || s.phone
      const channels = s.phone ? [{ type: 'whatsapp', value: s.phone }] : []
      const res = await apiCall('POST', `/bots/${botId}/contacts`, { name, channels }).catch(() => null)
      if (res?.id) {
        await apiCall('DELETE', `/empresa/${botId}/suggested-contacts/${encodeURIComponent(name)}`, null).catch(() => null)
        setSuggested(prev => prev.filter(x => (x.name || x.phone) !== name))
      }
    }
    setAddingAll(false)
    loadContacts()
  }

  return (
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

      <div style={{ padding: '8px 20px 4px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {suggested.length > 0 && (
          <button className="btn-ghost btn-sm" onClick={() => setShowSuggested(s => !s)}>
            {showSuggested ? '▲' : '▼'} Sugeridos ({suggested.length})
          </button>
        )}
        {waConns.some(c => c.status === 'ready') && (
          <button className="btn-ghost btn-sm" onClick={handleImportWA} disabled={importing}
            title="Lee los chats del sidebar de WA Web e importa los contactos como sugeridos">
            {importing ? 'Importando...' : '↓ Importar desde WA'}
          </button>
        )}
        {suggested.length > 0 && (
          <button className="btn-ghost btn-sm" onClick={handleAddAll} disabled={addingAll}
            title="Agrega todos los sugeridos como contactos de una sola vez">
            {addingAll ? 'Agregando...' : `+ Agregar todos (${suggested.length})`}
          </button>
        )}
        {suggested.length > 0 && (
          <button className="btn-ghost btn-sm" onClick={handleClearSuggested}
            title="Elimina todos los sugeridos para reimportar desde cero">
            🗑 Limpiar
          </button>
        )}
        {importMsg && <span style={{ fontSize: 12, color: '#64748b' }}>{importMsg}</span>}
      </div>

      {suggested.length > 0 && showSuggested && (
        <div style={{ padding: '0 20px 8px' }}>
          <div className="suggested-list">
            {suggested.map((s, i) => {
              const prevHasMsg = i > 0 ? suggested[i - 1].has_messages : s.has_messages
              const showSep = i > 0 && prevHasMsg && !s.has_messages
              return (
                <>
                  {showSep && (
                    <div key={`sep-${i}`} style={{ borderTop: '1px solid #334155', margin: '6px 0', opacity: 0.5 }} />
                  )}
                  <div key={s.phone || s.name || i} className="suggested-item" style={{ flexWrap: 'wrap', gap: 4 }}>
                    <span style={{ flex: 1, minWidth: 0 }}>
                      {s.name || s.phone}
                      {s.phone && s.name && <small style={{ color: '#94a3b8' }}> ({s.phone})</small>}
                      {s.has_messages && <small style={{ color: '#22c55e', marginLeft: 4 }}>●</small>}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                      <button className="btn-ghost btn-sm" onClick={() => handleAddSuggested(s)}>+ Agregar</button>
                      {(() => {
                        const key = s.phone || s.name
                        if (excludeState?.contactKey === key && excludeState.flows === null)
                          return <span style={{ fontSize: 11, color: '#94a3b8' }}>cargando...</span>
                        if (excludeState?.contactKey === key && excludeState.flows?.length > 0)
                          return <select
                            autoFocus
                            style={{ fontSize: 11, background: '#1e293b', border: '1px solid #475569', borderRadius: 4, color: '#e2e8f0', padding: '2px 4px', cursor: 'pointer' }}
                            defaultValue=""
                            onChange={async e => {
                              const flowId = e.target.value
                              if (!flowId) return
                              const flow = excludeState.flows.find(f => String(f.id) === flowId)
                              if (flow) {
                                await _applyExclusion(flow, excludeState.contactName)
                                setSuggested(prev => prev.filter(x => (x.phone || x.name) !== key))
                              }
                              setExcludeState(null)
                            }}
                            onBlur={() => setExcludeState(null)}
                          >
                            <option value="" disabled>excluir de...</option>
                            {excludeState.flows.map(f => (
                              <option key={f.id} value={String(f.id)}>{f.name}</option>
                            ))}
                          </select>
                        return <button className="btn-ghost btn-sm" style={{ color: '#f87171' }} onClick={() => handleExclude(s)}>Excluir</button>
                      })()}
                    </div>
                  </div>
                </>
              )
            })}
          </div>
        </div>
      )}

      <div className="ec-add-row">
        <button className="btn-primary btn-sm" onClick={() => setContactModal('new')}>+ Nuevo contacto</button>
      </div>

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
