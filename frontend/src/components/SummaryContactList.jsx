import { useState, useEffect } from 'react'

export default function SummaryContactList({ botId, apiCall, onSelect }) {
  const [contacts, setContacts] = useState(null)

  useEffect(() => {
    setContacts(null)
    apiCall('GET', `/summarizer/${botId}`, null)
      .then(data => {
        const raw = data?.contacts ?? []
        setContacts(raw.map(c => typeof c === 'string' ? { phone: c, name: c } : c))
      })
      .catch(() => setContacts([]))
  }, [botId])

  if (contacts === null) {
    return <div className="sv-contacts-empty">Cargando...</div>
  }

  if (contacts.length === 0) {
    return <div className="sv-contacts-empty">Sin resúmenes acumulados</div>
  }

  return (
    <div className="sv-contact-list">
      {contacts.map(({ phone, name }) => (
        <div
          key={phone}
          className="sv-contact-item"
          onClick={() => onSelect({ phone, name })}
        >
          <div className="sv-contact-item-avatar">
            {name.slice(0, 2).toUpperCase()}
          </div>
          <div className="sv-contact-item-info">
            <span className="sv-contact-item-name">{name}</span>
          </div>
          <span className="sv-contact-item-arrow">›</span>
        </div>
      ))}
    </div>
  )
}
