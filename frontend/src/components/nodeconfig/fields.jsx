/**
 * Campos del panel de configuración de nodos.
 *
 * Field es dinámico: renderiza según field.type (string, textarea, select,
 * float, number, bool, list, json, connection_select, contact_filter,
 * google_account_select, info). Los tipos custom reciben sus datos via
 * props _connections/_contacts/_google_accounts inyectadas por ConfigForm.
 */
import { useState, useEffect } from 'react'
import ContactFilterEditor from '../ContactFilterEditor.jsx'
import { S } from './styles.js'

// ─── Visibilidad condicional ──────────────────────────────────────────────────

/**
 * show_if viene del backend como { campo: valor }.
 * El campo es visible si TODOS los pares se cumplen en config.
 */
export function isVisible(field, config) {
  if (!field.show_if) return true
  return Object.entries(field.show_if).every(([k, v]) => config[k] === v)
}

// ─── Botón copiar con feedback ────────────────────────────────────────────────

export function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    if (!text) return
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button
      onClick={copy}
      style={{
        fontSize: 10, padding: '2px 7px', borderRadius: 4, cursor: 'pointer',
        background: copied ? '#166534' : 'transparent',
        border: `1px solid ${copied ? '#16a34a' : '#334155'}`,
        color: copied ? '#4ade80' : '#64748b',
        flexShrink: 0, transition: 'all 0.2s',
      }}
    >
      {copied ? 'Copiado' : 'Copiar'}
    </button>
  )
}

// ─── Campo JSON editable ──────────────────────────────────────────────────────

export function JsonField({ field, value, set, labelEl }) {
  const { hint } = field
  const [raw, setRaw]     = useState(JSON.stringify(value, null, 2))
  const [error, setError] = useState(null)

  // Sync externo → local (cuando el nodo cambia)
  useEffect(() => {
    setRaw(JSON.stringify(value, null, 2))
    setError(null)
  }, [JSON.stringify(value)])

  function handleChange(text) {
    setRaw(text)
    try {
      const parsed = JSON.parse(text)
      setError(null)
      set(parsed)
    } catch {
      setError('JSON inválido')
    }
  }

  return (
    <div style={S.fieldWrap}>
      {labelEl}
      <textarea
        style={{
          ...S.textarea,
          minHeight: 160,
          fontFamily: 'monospace',
          fontSize: 11,
          border: error ? '1px solid #ef4444' : S.textarea.border,
        }}
        value={raw}
        onChange={e => handleChange(e.target.value)}
        spellCheck={false}
      />
      {error && <span style={{ ...S.hint, color: '#ef4444' }}>{error}</span>}
      {!error && hint && <span style={S.hint}>{hint}</span>}
    </div>
  )
}

// ─── Selector de cuenta Google (con instrucciones de compartir) ───────────────

function GoogleAccountField({ value, set, labelEl, accounts }) {
  const selected = accounts.find(a => a.id === value) || accounts[0]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={S.fieldWrap}>
        {labelEl}
        {accounts.length === 0 ? (
          <span style={{ fontSize: 11, color: '#ef4444' }}>
            No hay cuentas Google configuradas (falta GOOGLE_SERVICE_ACCOUNT_JSON en .env)
          </span>
        ) : (
          <select style={S.select} value={value} onChange={e => set(e.target.value)}>
            {accounts.map(a => (
              <option key={a.id} value={a.id}>{a.label} — {a.email}</option>
            ))}
          </select>
        )}
      </div>
      {selected && (
        <div style={{
          background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6,
          padding: '7px 10px', display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          <span style={{ fontSize: 10, color: '#60a5fa', fontWeight: 700, letterSpacing: '0.06em' }}>
            COMPARTIR PLANILLA CON PULPO
          </span>
          <span style={{ fontSize: 10, color: '#64748b', lineHeight: 1.5 }}>
            Para que este nodo pueda acceder a tu Google Sheet, compartila con este email:
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
              {selected.email}
            </span>
            <CopyButton text={selected.email} />
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Bloque informativo copiable ──────────────────────────────────────────────

function InfoField({ label, hint }) {
  return (
    <div style={{
      background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6,
      padding: '7px 10px', display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <span style={{ fontSize: 10, color: '#60a5fa', fontWeight: 700, letterSpacing: '0.06em' }}>
        {label.toUpperCase()}
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
          {hint || label}
        </span>
        <CopyButton text={hint || label} />
      </div>
    </div>
  )
}

// ─── Render de un campo ───────────────────────────────────────────────────────

export function Field({ field, config, onChange }) {
  const { key, label, type, hint, rows = 4, options = [], required } = field
  const value = config[key] ?? field.default ?? (type === 'bool' ? false : type === 'list' ? [] : type === 'json' ? [] : '')

  function set(val) { onChange({ ...config, [key]: val }) }

  const labelEl = (
    <label style={S.label}>
      {label.toUpperCase()}{required && <span style={{ color: '#ef4444' }}> *</span>}
    </label>
  )

  if (type === 'json') return (
    <JsonField field={field} value={value} set={set} labelEl={labelEl} />
  )

  if (type === 'textarea') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <textarea
        style={S.textarea}
        rows={rows}
        value={value}
        onChange={e => set(e.target.value)}
        placeholder={hint || ''}
      />
    </div>
  )

  if (type === 'select') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <select style={S.select} value={value} onChange={e => set(e.target.value)}>
        {options.map(o => {
          const val = typeof o === 'object' ? o.value : o
          const lbl = typeof o === 'object' ? o.label : o
          return <option key={val} value={val}>{lbl}</option>
        })}
      </select>
    </div>
  )

  if (type === 'float') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="number"
        step="0.1"
        value={value}
        onChange={e => set(parseFloat(e.target.value) || 0)}
      />
    </div>
  )

  if (type === 'number') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="number"
        step="1"
        min="0"
        value={value}
        onChange={e => set(parseFloat(e.target.value) || 0)}
      />
      {hint && <span style={S.hint}>{hint}</span>}
    </div>
  )

  if (type === 'bool') return (
    <div style={S.fieldWrap}>
      <div style={S.checkRow}>
        <input
          id={key}
          type="checkbox"
          checked={!!value}
          onChange={e => set(e.target.checked)}
          style={{ accentColor: '#6b21a8', cursor: 'pointer' }}
        />
        <label htmlFor={key} style={{ ...S.label, margin: 0, cursor: 'pointer', fontSize: 12, color: '#cbd5e1', fontWeight: 400, letterSpacing: 0 }}>
          {label}
        </label>
      </div>
    </div>
  )

  if (type === 'list') {
    const csv = Array.isArray(value) ? value.join(', ') : value
    return (
      <div style={S.fieldWrap}>
        {labelEl}
        <input
          style={S.input}
          type="text"
          value={csv}
          onChange={e => set(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
          placeholder={hint || 'val1, val2, val3'}
        />
        {hint && <span style={S.hint}>{hint}</span>}
      </div>
    )
  }

  // Tipos custom — ConfigForm inyecta los datos en props _connections/_contacts/etc.
  if (type === 'connection_select') {
    const connections = field._connections || []
    return (
      <div style={S.fieldWrap}>
        {labelEl}
        <select style={S.select} value={value} onChange={e => set(e.target.value)}>
          <option value="">— Sin conexión —</option>
          {connections.map(c => (
            <option key={c.id} value={c.id}>{c.number || c.id}</option>
          ))}
        </select>
      </div>
    )
  }

  if (type === 'contact_filter') {
    return (
      <div style={S.fieldWrap}>
        {labelEl}
        <ContactFilterEditor
          value={value}
          onChange={cf => set(cf)}
          contacts={field._contacts || []}
          suggested={field._suggested || []}
          allowMass={field._allow_mass ?? false}
        />
      </div>
    )
  }

  if (type === 'google_account_select') {
    return <GoogleAccountField value={value} set={set} labelEl={labelEl} accounts={field._google_accounts || []} />
  }

  if (type === 'info') {
    return <InfoField label={label} hint={hint} />
  }

  // string (default)
  return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="text"
        value={value}
        onChange={e => set(e.target.value)}
        placeholder={hint || ''}
      />
      {hint && <span style={S.hint}>{hint}</span>}
    </div>
  )
}
