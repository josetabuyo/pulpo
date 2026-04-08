/**
 * FlowHeader — barra superior del editor.
 *
 * Muestra: nombre del flow | selector conexión | filtro de contactos | botón Guardar
 *
 * Filtro de contactos — flags independientes combinables:
 *   include_all_known: todos los contactos registrados
 *   include_unknown:   desconocidos (no en la DB de contactos)
 *   included[]:        phones específicos siempre incluidos
 *   excluded[]:        phones específicos siempre excluidos (prioridad máxima)
 */
import { useState, useEffect, useRef } from 'react'
import { useFlowStore } from '../store/flowStore.js'

const DEFAULT_FILTER = {
  include_all_known: false,
  include_unknown:   false,
  included:          [],
  excluded:          [],
}

function filterLabel(cf) {
  if (!cf) return 'Sin filtro'
  const parts = []
  if (cf.include_all_known) parts.push('todos conocidos')
  if (cf.include_unknown)   parts.push('desconocidos')
  if ((cf.included || []).length)  parts.push(`+${cf.included.length} incluidos`)
  if ((cf.excluded || []).length)  parts.push(`−${cf.excluded.length} excluidos`)
  if (parts.length === 0) return 'Sin filtro activo'
  return parts.join(', ')
}

function filterIsEmpty(cf) {
  if (!cf) return true
  return !cf.include_all_known && !cf.include_unknown
    && !(cf.included || []).length && !(cf.excluded || []).length
}

// ─── ContactFilterPicker ──────────────────────────────────────────────────────

function ContactFilterPicker({ value, onChange, contacts, style }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const cf = value || DEFAULT_FILTER

  useEffect(() => {
    function onClickOut(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClickOut)
    return () => document.removeEventListener('mousedown', onClickOut)
  }, [])

  function toggle(field) {
    onChange({ ...cf, [field]: !cf[field] })
  }

  function toggleContact(list, phone) {
    const arr = cf[list] || []
    const next = arr.includes(phone) ? arr.filter(p => p !== phone) : [...arr, phone]
    onChange({ ...cf, [list]: next })
  }

  const label = filterLabel(cf)
  const isEmpty = filterIsEmpty(cf)
  const allInclusive = cf.include_all_known && cf.include_unknown && !(cf.excluded || []).length

  // Contactos disponibles — identificados por nombre (reconocible para el usuario)
  // El sistema soporta nombres o números como identificadores
  const contactOptions = contacts.map(c => ({ id: c.name, label: c.name }))

  const inputStyle = {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 13,
    padding: '5px 8px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    maxWidth: 220,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    userSelect: 'none',
  }

  return (
    <div ref={ref} style={{ position: 'relative', ...style }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          ...inputStyle,
          borderColor: isEmpty ? '#475569' : '#6366f1',
          color: isEmpty ? '#64748b' : '#e2e8f0',
        }}
        title={label}
      >
        👥 {label}
      </div>

      {open && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          zIndex: 100,
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: 8,
          padding: '12px 14px',
          width: 300,
          boxShadow: '0 8px 24px rgba(0,0,0,.5)',
          marginTop: 4,
        }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '.04em' }}>
            Filtro de contactos
          </div>

          {/* ── Toggles globales ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
            <CheckRow
              checked={!!cf.include_all_known}
              onChange={() => toggle('include_all_known')}
              label="Todos los contactos conocidos"
            />
            <CheckRow
              checked={!!cf.include_unknown}
              onChange={() => toggle('include_unknown')}
              label="Desconocidos (no registrados)"
            />
          </div>

          {/* ── Incluidos específicos ── */}
          {(contactOptions.length > 0 || (cf.included || []).filter(p => !contactOptions.some(o => o.id === p)).length > 0) && (
            <Section title="Incluir específicamente">
              {contactOptions.map(opt => (
                <CheckRow
                  key={opt.id}
                  checked={(cf.included || []).includes(opt.id)}
                  onChange={() => toggleContact('included', opt.id)}
                  label={opt.label}
                />
              ))}
              {/* Incluidos por nombre literal (sin contacto registrado — ej: alias de WA) */}
              {(cf.included || []).filter(p => !contactOptions.some(o => o.id === p)).map(p => (
                <CheckRow
                  key={p}
                  checked
                  onChange={() => toggleContact('included', p)}
                  label={p}
                />
              ))}
            </Section>
          )}

          {/* ── Excluidos ── */}
          {(contactOptions.length > 0 || (cf.excluded || []).length > 0) && (
            <Section title="Excluir siempre (prioridad máxima)">
              {contactOptions
                .filter(opt => !(cf.included || []).includes(opt.id))
                .map(opt => (
                  <CheckRow
                    key={opt.id}
                    checked={(cf.excluded || []).includes(opt.id)}
                    onChange={() => toggleContact('excluded', opt.id)}
                    label={opt.label}
                    red
                  />
                ))}
              {/* Excluidos obsoletos */}
              {(cf.excluded || []).filter(p => !contactOptions.some(o => o.id === p)).map(p => (
                <CheckRow
                  key={p}
                  checked
                  onChange={() => toggleContact('excluded', p)}
                  label={`${p} (obsoleto)`}
                  red
                  italic
                />
              ))}
            </Section>
          )}

          {/* ── Warnings ── */}
          {isEmpty && (
            <Warning>Sin filtro activo — el flow no responderá a nadie.</Warning>
          )}
          {allInclusive && (
            <Warning yellow>Todos los contactos + desconocidos + sin exclusiones — responde a cualquiera.</Warning>
          )}
        </div>
      )}
    </div>
  )
}

function CheckRow({ checked, onChange, label, red, italic }) {
  return (
    <label style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      fontSize: 13,
      color: red ? '#f87171' : '#cbd5e1',
      cursor: 'pointer',
      userSelect: 'none',
    }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        style={{ flexShrink: 0, width: 14, height: 14, cursor: 'pointer', accentColor: red ? '#f87171' : undefined }}
      />
      <span style={italic ? { fontStyle: 'italic', opacity: 0.7 } : undefined}>{label}</span>
    </label>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 6, fontWeight: 600 }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>{children}</div>
    </div>
  )
}

function Warning({ children, yellow }) {
  return (
    <div style={{
      fontSize: 11,
      color: yellow ? '#f59e0b' : '#ef4444',
      background: yellow ? 'rgba(245,158,11,.08)' : 'rgba(239,68,68,.08)',
      borderRadius: 5,
      padding: '5px 8px',
      marginTop: 8,
    }}>
      ⚠ {children}
    </div>
  )
}

// ─── FlowHeader ───────────────────────────────────────────────────────────────

export default function FlowHeader({ flow, connections, apiCall, onSaved, onBack }) {
  const [name, setName]           = useState(flow.name || '')
  const [connectionId, setConn]   = useState(flow.connection_id || '')
  const [contactFilter, setCF]    = useState(flow.contact_filter || DEFAULT_FILTER)
  const [contacts, setContacts]   = useState([])
  const [saving, setSaving]       = useState(false)
  const [saveErr, setSaveErr]     = useState('')

  const isDirty       = useFlowStore(s => s.isDirty)
  const getDefinition = useFlowStore(s => s.getDefinition)
  const markClean     = useFlowStore(s => s.markClean)

  useEffect(() => {
    apiCall('GET', `/bots/${flow.empresa_id}/contacts`, null)
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
        name:           name.trim(),
        definition,
        connection_id:  connectionId || null,
        contact_filter: contactFilter,
      })
      markClean()
      onSaved?.()
    } catch {
      setSaveErr('Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 13,
    padding: '5px 8px',
  }

  return (
    <div style={{
      display:    'flex',
      alignItems: 'center',
      gap:        8,
      padding:    '8px 12px',
      background: '#0f172a',
      borderBottom: '1px solid #1e293b',
      flexShrink: 0,
      minWidth:   0,
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
        style={{ ...inputStyle, cursor: 'pointer', width: 140, flexShrink: 1 }}
        title="Activa solo para esta conexión"
      >
        <option value="">Todas las conexiones</option>
        {(connections || []).map(c => (
          <option key={c.id} value={c.id}>{c.number || c.id}</option>
        ))}
      </select>

      {/* Filtro de contactos */}
      <ContactFilterPicker
        value={contactFilter}
        onChange={cf => { setCF(cf); useFlowStore.setState({ isDirty: true }) }}
        contacts={contacts}
        style={{ flexShrink: 1 }}
      />

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
