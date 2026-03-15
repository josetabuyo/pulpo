/**
 * ChatWidget — chat colapsable reutilizable.
 *
 * Props:
 *   title        string        — nombre del contacto o label del chat
 *   subtitle     string?       — teléfono u otra info secundaria
 *   messages     Array         — [{ id, body, outbound, from, time }]
 *   onSend       async(text)   — callback para enviar; devuelve true/false
 *   defaultOpen  bool          — abierto por defecto
 *   extra        ReactNode?    — slot antes del input (ej: campo "Nombre" del sim)
 *   emptyText    string?       — texto cuando no hay mensajes
 *   unreadCount  number?       — badge en el header cuando está colapsado
 */
import { useEffect, useRef, useState } from 'react'

export default function ChatWidget({
  title,
  subtitle,
  messages = [],
  onSend,
  defaultOpen = false,
  extra = null,
  emptyText = 'Sin mensajes aún',
  unreadCount = 0,
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, open])

  async function handleSend(e) {
    e?.preventDefault()
    if (!text.trim() || sending) return
    setSending(true)
    await onSend(text)
    setText('')
    setSending(false)
  }

  return (
    <div className={`cw ${open ? 'cw--open' : 'cw--closed'}`}>
      {/* Header — siempre visible */}
      <button className="cw-header" onClick={() => setOpen(o => !o)}>
        <div className="cw-header-info">
          <span className="cw-title">{title}</span>
          {subtitle && <span className="cw-subtitle">{subtitle}</span>}
        </div>
        <div className="cw-header-right">
          {!open && unreadCount > 0 && (
            <span className="cw-unread-badge">{unreadCount}</span>
          )}
          <span className="cw-chevron">{open ? '▲ cerrar' : '▼ abrir'}</span>
        </div>
      </button>

      {/* Body — solo cuando está abierto */}
      {open && (
        <>
          <div className="cw-messages">
            {messages.length === 0 && (
              <div className="cw-empty">{emptyText}</div>
            )}
            {messages.map((m, i) => (
              <div key={m.id ?? i} className={`cw-bubble ${m.outbound ? 'cw-bubble--out' : 'cw-bubble--in'}`}>
                {!m.outbound && m.from && (
                  <span className="cw-bubble-from">{m.from}</span>
                )}
                <div className="cw-bubble-body">{m.body}</div>
                <div className="cw-bubble-time">{m.time}</div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          <form className="cw-input-row" onSubmit={handleSend}>
            {extra}
            <input
              type="text"
              placeholder="Escribí un mensaje..."
              value={text}
              onChange={e => setText(e.target.value)}
              disabled={sending}
              autoFocus
            />
            <button type="submit" className="btn-primary btn-sm" disabled={sending || !text.trim()}>
              Enviar
            </button>
          </form>
        </>
      )}
    </div>
  )
}
