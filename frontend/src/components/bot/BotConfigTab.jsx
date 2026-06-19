/**
 * Tab "Configurar" del portal de bot: nombre y contraseña.
 */
import { useState, useEffect } from 'react'

export default function BotConfigTab({ botId, botName, apiCall, onNameChange }) {
  const [form, setForm] = useState({ name: botName, newPassword: '', confirmPassword: '' })
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    apiCall('GET', `/bot/${botId}`, null).then(r => {
      if (r?.bot_name) setForm(f => ({ ...f, name: r.bot_name }))
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
    if (Object.keys(body).length === 0) { setSaving(false); return }
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
        <div className="fg"><label>Nombre de la bot</label>
          <input value={form.name} onChange={set('name')} placeholder="Nombre" />
        </div>
        <div className="fg"><label>Nueva contraseña <small style={{ fontWeight: 400, color: '#94a3b8' }}>(dejar vacío para no cambiar)</small></label>
          <input type="password" value={form.newPassword} onChange={set('newPassword')} placeholder="Nueva contraseña" />
        </div>
        {form.newPassword && (
          <div className="fg"><label>Confirmar contraseña</label>
            <input type="password" value={form.confirmPassword} onChange={set('confirmPassword')} placeholder="Repetir contraseña" />
          </div>
        )}
        <div className="portal-save-row">
          <button type="submit" className="btn-primary btn-sm" disabled={saving}>{saving ? 'Guardando...' : 'Guardar cambios'}</button>
          {result === 'ok' && <span className="portal-save-ok">✓ Guardado</span>}
          {result === 'pwd-mismatch' && <span className="portal-save-err">Las contraseñas no coinciden</span>}
          {result && result !== 'ok' && result !== 'pwd-mismatch' && <span className="portal-save-err">{result}</span>}
        </div>
      </form>
    </div>
  )
}
