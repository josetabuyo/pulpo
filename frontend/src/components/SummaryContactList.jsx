import { useState, useEffect } from 'react'

export default function SummaryContactList({ botId, apiCall, onSelect }) {
  const [contacts, setContacts] = useState(null)

  useEffect(() => {
    setContacts(null)
    apiCall('GET', `/summarizer/${botId}`, null)
      .then(data => setContacts(Array.isArray(data?.contacts) ? data.contacts : []))
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
      {contacts.map(phone => (
        <div
          key={phone}
          className="sv-contact-item"
          onClick={() => onSelect({ phone, name: phone })}
        >
          <div className="sv-contact-item-avatar">
            {phone.slice(-2)}
          </div>
          <div className="sv-contact-item-info">
            <span className="sv-contact-item-name">{phone}</span>
          </div>
          <span className="sv-contact-item-arrow">›</span>
        </div>
      ))}
    </div>
  )
}
