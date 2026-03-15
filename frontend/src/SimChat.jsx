import { useState, useEffect } from 'react'
import { api } from './api.js'
import ChatWidget from './components/ChatWidget.jsx'

export default function SimChat({ number, pwd, defaultOpen = false }) {
  const [messages, setMessages] = useState([])
  const [fromName, setFromName] = useState('Contacto')

  useEffect(() => {
    const iv = setInterval(async () => {
      const data = await api('GET', `/sim/messages/${number}`, null, pwd).catch(() => null)
      if (Array.isArray(data)) {
        setMessages(data.map((m, i) => ({
          id: i,
          body: m.text,
          outbound: m.role === 'bot',
          from: m.from_name,
          time: m.ts,
        })))
      }
    }, 1000)
    return () => clearInterval(iv)
  }, [number, pwd])

  async function handleSend(text) {
    await api('POST', `/sim/send/${number}`, { from_name: fromName, from_phone: '0000000000', text }, pwd)
      .catch(() => null)
  }

  const extra = (
    <input
      style={{ width: 90, flexShrink: 0, fontSize: 12 }}
      value={fromName}
      onChange={e => setFromName(e.target.value)}
      placeholder="Nombre"
    />
  )

  return (
    <ChatWidget
      title={`Simulador — +${number}`}
      messages={messages}
      onSend={handleSend}
      defaultOpen={defaultOpen}
      extra={extra}
      emptyText="Escribí un mensaje para simular una conversación"
    />
  )
}
