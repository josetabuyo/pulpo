import { useState } from 'react'
import SummaryView from './SummaryView.jsx'
import SummaryContactList from './SummaryContactList.jsx'

export default function UIsList({ botId, apiCall }) {
  const [selectedContact, setSelectedContact] = useState(null)

  if (selectedContact) {
    return (
      <SummaryView
        empresaId={botId}
        contactPhone={selectedContact.phone}
        contactName={selectedContact.name}
        apiCall={apiCall}
        onBack={() => setSelectedContact(null)}
      />
    )
  }

  return (
    <div>
      <SummaryContactList
        botId={botId}
        apiCall={apiCall}
        onSelect={contact => setSelectedContact(contact)}
      />
    </div>
  )
}
