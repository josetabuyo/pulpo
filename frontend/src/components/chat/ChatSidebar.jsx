/**
 * Lista de conversaciones del caller (solo fecha, pedido explícito -- ver
 * management/HANDOFF_DASHBOARD_CHATS_VIEW.md §2.3/§5.2, gitignoreado). La
 * activa resaltada, botón "+ Nueva conversación" arriba.
 */
function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

// 2026-08-05: pasa de columna siempre visible a drawer oculto por defecto
// (pedido explícito -- la UX de tener el historial siempre a la vista era
// mala). `onClose` cierra por backdrop o por Escape; el botón que lo abre
// vive en el header (ver PulpoChatWidget.jsx).
export default function ChatSidebar({ title, conversations, activeId, onSelect, onNew, open, onClose }) {
  return (
    <>
      {open && <div className="pc-sidebar-backdrop" onClick={onClose} />}
      <div className={`pc-sidebar ${open ? 'pc-sidebar--open' : ''}`}>
        <div className="pc-sidebar-header">
          <div className="pc-sidebar-title">{title}</div>
          <button className="pc-sidebar-close" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
        <button className="pc-new-btn" onClick={onNew}>+ Nueva conversación</button>
        <div className="pc-conv-list">
          {conversations.length === 0 && (
            <div className="pc-conv-empty">Sin conversaciones todavía</div>
          )}
          {conversations.map(c => (
            <button
              key={c.id}
              className={`pc-conv-item ${c.id === activeId ? 'pc-conv-item--active' : ''}`}
              onClick={() => onSelect(c.id)}
            >
              {formatDate(c.last_message_at || c.created_at)}
            </button>
          ))}
        </div>
      </div>
    </>
  )
}
