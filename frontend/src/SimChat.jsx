import { useState, useEffect, useRef } from 'react'
import { api } from './api.js'

export default function SimChat({ number, pwd }) {
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [fromName, setFromName] = useState('Contacto')
  const bottomRef = useRef(null)

  useEffect(() => {
    const interval = setInterval(async () => {
      const data = await api('GET', `/sim/messages/${number}`, null, pwd)
      if (Array.isArray(data)) setMessages(data)
    }, 1000)
    return () => clearInterval(interval)
  }, [number, pwd])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    if (!text.trim()) return
    await api('POST', `/sim/send/${number}`, { from_name: fromName, from_phone: '0000000000', text }, pwd)
    setText('')
  }

  return (
    <div className="sim-chat">
      <div className="sim-chat-header">💬 Simulador — como si fuera +{number}</div>
      <div className="sim-chat-messages">
        {messages.length === 0 && (
          <div className="sim-empty">Escribí un mensaje para simular una conversación</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`sim-msg sim-msg--${m.role}`}>
            <span className="sim-msg-from">{m.from_name}</span>
            <span className="sim-msg-text">{m.text}</span>
            <span className="sim-msg-ts">{m.ts}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="sim-chat-input">
        <input
          className="sim-name-input"
          value={fromName}
          onChange={e => setFromName(e.target.value)}
          placeholder="Nombre"
        />
        <input
          className="sim-text-input"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Escribí un mensaje..."
        />
        <button className="btn-primary btn-sm" onClick={send}>Enviar</button>
      </div>
    </div>
  )
}
