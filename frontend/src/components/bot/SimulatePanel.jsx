/**
 * Simulador in-band de mensajes (management/HANDOFF_SIMULACION_V2.md).
 *
 * Mandar un mensaje acá es equivalente a mandarlo por Telegram: el flow y el
 * trigger que aplican se resuelven solos (POST /flows/bots/{botId}/simulate),
 * igual que con un mensaje real. La única diferencia queda marcada con el
 * badge "SIMULADO" en la lista de ejecuciones (abajo) — no hay nada más para
 * elegir/configurar acá a propósito.
 */
import { useState } from 'react'

export default function SimulatePanel({ botId, apiCall, onSent }) {
  const [simId, setSimId]     = useState('')
  const [message, setMessage] = useState('')
  const [history, setHistory] = useState([]) // [{role: 'user'|'bot', text}]
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  function resetConversation() {
    setSimId('')
    setHistory([])
    setError('')
  }

  async function handleSubmit() {
    if (!message.trim() || loading) return
    setError('')
    setLoading(true)
    const userText = message
    try {
      const result = await apiCall('POST', `/flows/bots/${botId}/simulate`, {
        message: userText,
        sim_id: simId || undefined,
      })
      if (result?._status) {
        setError(result?.detail || 'Error al simular')
      } else {
        setHistory(h => [...h, { role: 'user', text: userText }, { role: 'bot', text: result.reply ?? '(sin respuesta)' }])
        if (result.sim_id) setSimId(result.sim_id)
        setMessage('')
        onSent?.()
      }
    } catch (e) {
      setError('Error al simular: ' + (e?.message || e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 8,
      border: '1px solid #e2e8f0', borderRadius: 8, padding: 10, marginBottom: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b', letterSpacing: '0.04em' }}>
          SIMULAR MENSAJE
        </span>
        {simId && (
          <button className="btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={resetConversation}>
            ↺ Nueva conversación
          </button>
        )}
      </div>

      {history.length > 0 && (
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 6,
          maxHeight: 200, overflowY: 'auto',
          background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: 8,
        }}>
          {history.map((m, i) => (
            <div
              key={i}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '85%',
                background: m.role === 'user' ? '#dbeafe' : '#fff',
                border: `1px solid ${m.role === 'user' ? '#93c5fd' : '#e2e8f0'}`,
                borderRadius: 8, padding: '5px 8px',
                fontSize: 12, color: '#334155', whiteSpace: 'pre-wrap',
              }}
            >
              {m.text}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6 }}>
        <input
          style={{
            flex: 1, border: '1px solid #cbd5e1', borderRadius: 6,
            padding: '6px 9px', fontSize: 13, outline: 'none',
          }}
          type="text"
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }}
          placeholder="Mensaje, como si lo mandaras por Telegram..."
        />
        <button
          className="btn-ghost btn-sm"
          onClick={handleSubmit}
          disabled={loading || !message.trim()}
          style={{ padding: '6px 14px', fontSize: 13 }}
        >
          {loading ? '⏳' : 'Enviar'}
        </button>
      </div>

      {error && <div style={{ fontSize: 11, color: '#dc2626' }}>{error}</div>}
    </div>
  )
}
