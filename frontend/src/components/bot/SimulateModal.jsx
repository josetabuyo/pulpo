/**
 * SimulateModal — "Simular" de un trigger de mensaje puntual (tab
 * Triggers, 2026-07-23). Reemplaza al viejo SimulatePanel fijo en
 * "Ejecuciones", que llamaba a un endpoint de matching global
 * (`/flows/bots/{botId}/simulate`) que nunca existió en el backend Next.js
 * -- acá se simula un trigger CONCRETO (flowId+nodeId, elegido en la fila
 * de Triggers), disparando directo por
 * `POST /api/flows/{flowId}/trigger/{nodeId}` (mismo endpoint que un
 * trigger HTTP real) con un `contact_phone` estable de simulación, y
 * poleando `GET /api/runs/{runId}` hasta que el run termina para leer la
 * respuesta del bot (`state.data.reply`, escrita por send_message).
 */
import { useState, useRef, useEffect } from 'react'

const POLL_MS = 1200
const MAX_POLLS = 25 // ~30s

function lastReplyFromSteps(steps) {
  if (!Array.isArray(steps)) return null
  for (let i = steps.length - 1; i >= 0; i--) {
    const reply = steps[i]?.output_state?.data?.reply
    if (reply) return reply
  }
  return null
}

export default function SimulateModal({ apiCall, flowId, nodeId, label, onClose }) {
  const [message, setMessage] = useState('')
  const [history, setHistory] = useState([]) // [{role: 'user'|'bot', text}]
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const contactRef = useRef(`sim:${crypto.randomUUID()}`)

  useEffect(() => () => { contactRef.current = null }, [])

  async function pollRun(runId) {
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, POLL_MS))
      const run = await apiCall('GET', `/runs/${runId}`, null).catch(() => null)
      if (!run?.status) continue
      if (run.status !== 'running') {
        return lastReplyFromSteps(run.steps)
      }
    }
    return null
  }

  async function handleSubmit() {
    if (!message.trim() || sending) return
    setError('')
    setSending(true)
    const userText = message
    setMessage('')
    setHistory(h => [...h, { role: 'user', text: userText }])
    try {
      const res = await apiCall('POST', `/flows/${flowId}/trigger/${nodeId}`, {
        message: userText,
        contact_phone: contactRef.current,
      }).catch(() => null)
      if (!res?.run_id) {
        setError(res?.error || 'Error al simular (¿el trigger está pausado?)')
        return
      }
      const reply = await pollRun(res.run_id)
      setHistory(h => [...h, { role: 'bot', text: reply ?? '(sin respuesta)' }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 480 }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <strong>Simular — {label}</strong>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        <div style={{
          display: 'flex', flexDirection: 'column', gap: 6,
          minHeight: 80, maxHeight: 320, overflowY: 'auto',
          background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6,
          padding: 8, marginBottom: 10,
        }}>
          {history.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-subtle)', textAlign: 'center', padding: '20px 0' }}>
              Mandá un mensaje como si viniera por este trigger.
            </div>
          )}
          {history.map((m, i) => (
            <div
              key={i}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '85%',
                background: m.role === 'user' ? 'rgba(46,166,218,.12)' : 'var(--surface)',
                border: `1px solid ${m.role === 'user' ? 'var(--tg)' : 'var(--border)'}`,
                borderRadius: 8, padding: '5px 8px',
                fontSize: 12, color: 'var(--text)', whiteSpace: 'pre-wrap',
              }}
            >
              {m.text}
            </div>
          ))}
          {sending && (
            <div style={{ alignSelf: 'flex-start', fontSize: 12, color: 'var(--text-subtle)' }}>…</div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 6 }}>
          <input
            style={{
              flex: 1, border: '1px solid var(--border-strong)', borderRadius: 6,
              padding: '6px 9px', fontSize: 13, outline: 'none',
            }}
            type="text"
            value={message}
            onChange={e => setMessage(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }}
            placeholder="Mensaje de prueba..."
            autoFocus
          />
          <button
            className="btn-ghost btn-sm"
            onClick={handleSubmit}
            disabled={sending || !message.trim()}
            style={{ padding: '6px 14px', fontSize: 13 }}
          >
            {sending ? '⏳' : 'Enviar'}
          </button>
        </div>

        {error && <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 6 }}>{error}</div>}
      </div>
    </div>
  )
}
