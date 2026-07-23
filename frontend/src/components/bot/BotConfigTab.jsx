/**
 * Tab "Configurar" del portal de bot: nombre, contraseña y mensaje de despedida.
 */
import { useState, useEffect } from 'react'

export default function BotConfigTab({ botId, botName, apiCall, onNameChange }) {
  const [form, setForm] = useState({
    name: botName,
    newPassword: '',
    confirmPassword: '',
    farewell_message: '',
    conversation_ttl_hours: 24,
  })
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    apiCall('GET', `/bot/${botId}`, null).then(r => {
      if (r?.bot_name) setForm(f => ({ ...f, name: r.bot_name }))
      if (r?.farewell_message !== undefined) setForm(f => ({ ...f, farewell_message: r.farewell_message }))
      if (r?.conversation_ttl_hours !== undefined) setForm(f => ({ ...f, conversation_ttl_hours: r.conversation_ttl_hours }))
    }).catch(e => console.warn('[BotConfigTab] carga', e))
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
    body.farewell_message = form.farewell_message
    const ttl = parseInt(form.conversation_ttl_hours, 10)
    if (ttl > 0) body.conversation_ttl_hours = ttl
    const res = await apiCall('PUT', `/bot/${botId}/config`, body).catch(() => null)
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
        <div className="fg">
          <label>Nombre de la bot</label>
          <input value={form.name} onChange={set('name')} placeholder="Nombre" />
        </div>

        <div className="fg">
          <label>
            Mensaje de despedida&nbsp;
            <small style={{ fontWeight: 400, color: 'var(--text-subtle)' }}>
              (se envía al usuario cuando la conversación expira por inactividad)
            </small>
          </label>
          <textarea
            value={form.farewell_message}
            onChange={set('farewell_message')}
            placeholder="Ej: ¡Hola! Tu consulta anterior se cerró. ¡Escribinos cuando quieras!"
            rows={5}
            style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', fontSize: 13, padding: '6px 8px', borderRadius: 6, border: '1px solid #e2e8f0', lineHeight: 1.5 }}
          />
          <small style={{ color: 'var(--text-subtle)', fontSize: 11 }}>
            Vacío = usa el mensaje por defecto del sistema.
          </small>
        </div>

        <div className="fg">
          <label>
            Tiempo de vida de conversación (horas)&nbsp;
            <small style={{ fontWeight: 400, color: 'var(--text-subtle)' }}>
              (disponible con <code>{'{{_conv_ttl_hours}}'}</code> en nodos del flow)
            </small>
          </label>
          <input
            type="number"
            min="1"
            max="168"
            value={form.conversation_ttl_hours}
            onChange={e => setForm(f => ({ ...f, conversation_ttl_hours: e.target.value }))}
            style={{ width: 100 }}
          />
          <small style={{ color: 'var(--text-subtle)', fontSize: 11 }}>horas — default: 24</small>
        </div>

        <div className="fg">
          <label>
            Nueva contraseña&nbsp;
            <small style={{ fontWeight: 400, color: 'var(--text-subtle)' }}>(dejar vacío para no cambiar)</small>
          </label>
          <input type="password" value={form.newPassword} onChange={set('newPassword')} placeholder="Nueva contraseña" />
        </div>
        {form.newPassword && (
          <div className="fg">
            <label>Confirmar contraseña</label>
            <input type="password" value={form.confirmPassword} onChange={set('confirmPassword')} placeholder="Repetir contraseña" />
          </div>
        )}

        <div className="portal-save-row">
          <button type="submit" className="btn-primary btn-sm" disabled={saving}>
            {saving ? 'Guardando...' : 'Guardar cambios'}
          </button>
          {result === 'ok' && <span className="portal-save-ok">✓ Guardado</span>}
          {result === 'pwd-mismatch' && <span className="portal-save-err">Las contraseñas no coinciden</span>}
          {result && result !== 'ok' && result !== 'pwd-mismatch' && <span className="portal-save-err">{result}</span>}
        </div>
      </form>
    </div>
  )
}
