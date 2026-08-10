import { useState } from 'react'
import { chatApi } from '../../lib/chatApi.js'

// Interpolación mínima client-side, solo para textos de UI (confirm_text/
// success_text) -- el lead en sí lo arma y firma el server (ver
// web/lib/business/chat-directory.ts). Nunca confiar en esto para nada que
// importe.
function fill(tpl, item) {
  if (!tpl) return ''
  return tpl.replace(/\{\{item\.(\w+)\}\}/g, (m, key) => (item?.[key] ?? m))
}

function Field({ field, value, onChange }) {
  const common = {
    id: `pc-dir-field-${field.name}`,
    value: value ?? '',
    placeholder: field.placeholder || '',
    onChange: e => onChange(e.target.value),
  }
  return (
    <label className="pc-dir-field">
      <span>{field.label}{field.required && ' *'}</span>
      {field.type === 'textarea' ? (
        <textarea rows={3} {...common} />
      ) : field.type === 'select' ? (
        <select {...common}>
          <option value="" disabled>Elegí una opción</option>
          {(field.options || []).map(opt => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      ) : (
        <input type={field.type === 'tel' ? 'tel' : field.type === 'email' ? 'email' : 'text'} {...common} />
      )}
    </label>
  )
}

/**
 * Modal de conexión: confirma directo (sin fields) o pide un mini-form
 * (ej. "Dirección" para servicios) antes de disparar el lead. Camino
 * paralelo al chat conversacional -- ver ChatDirectory.jsx.
 */
export default function ChatDirectoryConnect({ botId, chatId, sectionId, item, connectConfig, onClose }) {
  const [values, setValues] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const fields = connectConfig.fields || []
  const missingRequired = fields.some(f => f.required && !String(values[f.name] || '').trim())

  async function handleConnect() {
    setSubmitting(true)
    setError('')
    const res = await chatApi.directoryConnect(botId, chatId, sectionId, {
      item_id: item.id,
      item_token: item.item_token,
      item_raw: item.raw || {},
      fields: values,
    })
    setSubmitting(false)
    if (!res._ok) {
      setError(res.detail || res.error || 'No se pudo conectar. Probá de nuevo.')
      return
    }
    setResult(res)
  }

  return (
    <div className="pc-dir-modal-overlay" onClick={onClose}>
      <div className="pc-dir-modal" onClick={e => e.stopPropagation()}>
        <button className="pc-dir-modal-close" onClick={onClose} aria-label="Cerrar">×</button>

        {result ? (
          <div className="pc-dir-modal-success">
            <div className="pc-dir-modal-success-icon">✓</div>
            <p>{result.message || 'Listo, ya avisamos.'}</p>
            <button className="pc-dir-connect-btn" onClick={onClose}>Cerrar</button>
          </div>
        ) : (
          <>
            <h3 className="pc-dir-modal-title">{item.title}</h3>
            {item.subtitle && <p className="pc-dir-modal-subtitle">{item.subtitle}</p>}
            {connectConfig.confirm_text && <p className="pc-dir-modal-confirm">{fill(connectConfig.confirm_text, item)}</p>}

            {fields.length > 0 && (
              <div className="pc-dir-fields">
                {fields.map(f => (
                  <Field key={f.name} field={f} value={values[f.name]} onChange={v => setValues(prev => ({ ...prev, [f.name]: v }))} />
                ))}
              </div>
            )}

            {error && <div className="pc-dir-modal-error">{error}</div>}

            <button
              className="pc-dir-connect-btn"
              disabled={submitting || missingRequired}
              onClick={handleConnect}
            >
              {submitting ? 'Conectando…' : connectConfig.label}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
