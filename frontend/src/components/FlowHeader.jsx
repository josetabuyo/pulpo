/**
 * FlowHeader — barra superior del editor.
 *
 * Muestra: nombre del flow (editable) | selector connection | selector contact | botón Guardar
 */
import { useState, useEffect } from 'react'
import { useFlowStore } from '../store/flowStore.js'

export default function FlowHeader({ flow, connections, apiCall, onSaved, onBack }) {
  const [name, setName]             = useState(flow.name || '')
  const [connectionId, setConn]     = useState(flow.connection_id || '')
  const [contactPhone, setContact]  = useState(flow.contact_phone || '')
  const [contacts, setContacts]     = useState([])
  const [saving, setSaving]         = useState(false)
  const [saveErr, setSaveErr]       = useState('')

  const isDirty      = useFlowStore(s => s.isDirty)
  const getDefinition = useFlowStore(s => s.getDefinition)
  const markClean    = useFlowStore(s => s.markClean)

  // Cargar contactos de la empresa para el selector
  useEffect(() => {
    const empresaId = flow.empresa_id
    apiCall('GET', `/bots/${empresaId}/contacts`, null)
      .then(res => { if (Array.isArray(res)) setContacts(res) })
      .catch(() => {})
  }, [flow.empresa_id])

  async function handleSave() {
    if (!name.trim()) { setSaveErr('El nombre es obligatorio'); return }
    setSaving(true)
    setSaveErr('')
    try {
      const definition = getDefinition()
      await apiCall('PUT', `/empresas/${flow.empresa_id}/flows/${flow.id}`, {
        name: name.trim(),
        definition,
        connection_id: connectionId || null,
        contact_phone: contactPhone || null,
      })
      markClean()
      onSaved?.()
    } catch {
      setSaveErr('Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  // Extraer números de teléfono de los contactos para el selector
  const contactOptions = contacts.flatMap(c =>
    (c.channels || [])
      .filter(ch => ch.type === 'whatsapp' || ch.type === 'telegram')
      .map(ch => ({ value: ch.value, label: `${c.name} (${ch.value})` }))
  )

  const inputStyle = {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 13,
    padding: '5px 8px',
  }

  const selectStyle = { ...inputStyle, cursor: 'pointer' }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '8px 12px',
      background: '#0f172a',
      borderBottom: '1px solid #1e293b',
      flexShrink: 0,
      minWidth: 0,
    }}>
      {/* Volver */}
      <button
        onClick={onBack}
        style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: '0 2px', flexShrink: 0 }}
        title="Volver"
      >←</button>

      {/* Nombre */}
      <input
        value={name}
        onChange={e => setName(e.target.value)}
        placeholder="Nombre del flow"
        style={{ ...inputStyle, width: 180, flexShrink: 1 }}
      />

      <div style={{ width: 1, height: 20, background: '#1e293b', flexShrink: 0 }} />

      {/* Conexión */}
      <select
        value={connectionId}
        onChange={e => setConn(e.target.value)}
        style={{ ...selectStyle, width: 140, flexShrink: 1 }}
        title="Activa solo para esta conexión"
      >
        <option value="">Todas las conexiones</option>
        {(connections || []).map(c => (
          <option key={c.id} value={c.id}>{c.number || c.id}</option>
        ))}
      </select>

      {/* Contacto */}
      <select
        value={contactPhone}
        onChange={e => setContact(e.target.value)}
        style={{ ...selectStyle, width: 160, flexShrink: 1 }}
        title="Activa solo para este contacto"
      >
        <option value="">Todos los contactos</option>
        {contactOptions.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {/* Guardar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto', flexShrink: 0 }}>
        {saveErr && <span style={{ fontSize: 11, color: '#ef4444' }}>{saveErr}</span>}
        {isDirty && !saveErr && <span style={{ fontSize: 11, color: '#f59e0b' }}>Sin guardar</span>}
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            background: isDirty ? '#16a34a' : '#1e293b',
            border: '1px solid ' + (isDirty ? '#16a34a' : '#334155'),
            borderRadius: 6,
            color: isDirty ? '#fff' : '#64748b',
            fontSize: 13,
            padding: '5px 14px',
            cursor: saving ? 'default' : 'pointer',
            fontWeight: isDirty ? 600 : 400,
            transition: 'all 0.15s',
            whiteSpace: 'nowrap',
          }}
        >
          {saving ? 'Guardando...' : 'Guardar'}
        </button>
      </div>
    </div>
  )
}
