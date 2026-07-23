import { useEffect, useRef } from 'react'

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
}

/**
 * Burbujas user/bot + autoscroll + indicador "···" mientras el run está
 * `running`. bot = superficie fría (--pc-surface), usuario = superficie
 * cálida (--pc-wine-deep) -- ver §6 del handoff para el porqué.
 */
export default function ChatThread({ messages, runStatus, error }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, runStatus])

  return (
    <div className="pc-thread">
      {messages.map(m => (
        <div key={m.id} className={`pc-bubble-row pc-bubble-row--${m.role === 'user' ? 'user' : 'bot'}`}>
          <div className={`pc-bubble pc-bubble--${m.role === 'user' ? 'user' : 'bot'}`}>
            {m.content}
            <span className="pc-bubble-time">{formatTime(m.created_at)}</span>
          </div>
        </div>
      ))}

      {runStatus === 'running' && (
        <div className="pc-bubble-row pc-bubble-row--bot">
          <div className="pc-typing"><span /><span /><span /></div>
        </div>
      )}

      {error && (
        <div className="pc-status pc-status--error">⚠ {error}</div>
      )}

      <div ref={endRef} />
    </div>
  )
}
