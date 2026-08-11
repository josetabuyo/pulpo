import { useEffect, useRef, useState } from 'react'
import { chatApi } from '../../lib/chatApi.js'
import ChatDirectoryConnect from './ChatDirectoryConnect.jsx'
import ChatDirectoryDetail from './ChatDirectoryDetail.jsx'

const DEBOUNCE_MS = 300
const SCROLL_THRESHOLD_PX = 120
// Tab incorporado (no configurable por admin, ver chat-directory-types.ts
// validateSection -- "conversaciones" está reservado). Reemplaza al viejo
// botón "Historial" del header (2026-08-10): mismo dato, ahora vive acá
// para no tener dos formas distintas de llegar a lo mismo.
const CONVERSATIONS_TAB_ID = 'conversaciones'

function ItemCard({ item, onOpen }) {
  return (
    <button className="pc-dir-item" onClick={() => onOpen(item)}>
      {item.image_url && <img className="pc-dir-item-img" src={item.image_url} alt="" />}
      <div className="pc-dir-item-body">
        <div className="pc-dir-item-title">{item.title}</div>
        {item.subtitle && <div className="pc-dir-item-subtitle">{item.subtitle}</div>}
        {item.description && <div className="pc-dir-item-desc">{item.description}</div>}
        {item.meta && <div className="pc-dir-item-meta">{item.meta}</div>}
      </div>
    </button>
  )
}

function formatConvDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

function ConversationsPanel({ conversations, activeConversationId, onSelectConversation, onNewConversation }) {
  return (
    <div className="pc-dir-list">
      <button className="pc-new-btn" onClick={onNewConversation}>+ Nueva conversación</button>
      {conversations.length === 0 && <div className="pc-dir-status">Sin conversaciones todavía</div>}
      {conversations.map(c => (
        <button
          key={c.id}
          className={`pc-conv-item ${c.id === activeConversationId ? 'pc-conv-item--active' : ''}`}
          onClick={() => onSelectConversation(c.id)}
        >
          {formatConvDate(c.last_message_at || c.created_at)}
        </button>
      ))}
    </div>
  )
}

/**
 * Rail izquierdo, camino paralelo al chat conversacional: buscador + lista
 * por sección configurable (comercios/servicios/noticias, ver
 * web/lib/business/chat-directory-types.ts) más un tab incorporado de
 * "Conversaciones" (historial propio, siempre disponible, no configurable).
 * Cada sección de catálogo define su propio `mode`: "connect" (default)
 * dispara el mismo tipo de lead que hoy arma el nodo HTTP del flow al tocar
 * un item; "detail" abre una vista de solo lectura con link a la fuente
 * original, sin form ni lead -- pensado para listas tipo noticias. Genérico:
 * nada acá conoce a Luganense ni a ningún bot en particular, todo sale de la
 * config guardada en `chat_configs.directory` (salvo el tab de conversaciones,
 * que es infraestructura de Pulpo, no config de admin).
 *
 * Paginación (scroll infinito, 2026-08-10): una sección con `paginated: true`
 * (source.url usa {{offset}}, ver chat-directory-types.ts) pide la siguiente
 * página sola al llegar cerca del final de `.pc-dir-list`. Secciones sin eso
 * siguen igual que siempre -- un solo fetch, sin scroll infinito.
 */
export default function ChatDirectory({
  botId,
  chatId,
  directory,
  open,
  onToggle,
  conversations = [],
  activeConversationId,
  onSelectConversation,
  onNewConversation,
}) {
  const catalogSections = directory?.enabled ? directory.sections || [] : []
  const sections = [...catalogSections, { id: CONVERSATIONS_TAB_ID, label: 'Conversaciones', icon: '🕘', builtin: true }]

  const [activeId, setActiveId] = useState(sections[0]?.id || null)
  const [query, setQuery] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState('')
  const [connectItem, setConnectItem] = useState(null)
  const [detailItem, setDetailItem] = useState(null)

  const debounceRef = useRef(null)
  const listRef = useRef(null)
  const active = sections.find(s => s.id === activeId) || sections[0] || null
  const isConversations = active?.id === CONVERSATIONS_TAB_ID

  useEffect(() => {
    if (!activeId && sections[0]) setActiveId(sections[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogSections.length])

  useEffect(() => {
    setQuery('')
    setItems([])
    setError('')
    setHasMore(false)
  }, [activeId])

  useEffect(() => {
    if (!active || isConversations) return
    const trimmed = query.trim()
    const minLen = active.min_query_len ?? 0
    const shouldSearch = active.empty_query === 'hide' ? trimmed.length > 0 : trimmed.length >= minLen
    if (!shouldSearch) { setItems([]); setHasMore(false); return }

    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      setError('')
      const res = await chatApi.directorySearch(botId, chatId, active.id, trimmed, 0)
      setLoading(false)
      if (!res._ok) { setError('No se pudo buscar. Probá de nuevo.'); return }
      if (res.error) { setError(res.error); return }
      setItems(res.items || [])
      setHasMore(Boolean(active.paginated && res.has_more))
    }, DEBOUNCE_MS)

    return () => clearTimeout(debounceRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, active, botId, chatId])

  async function loadMore() {
    if (!active || !active.paginated || loading || loadingMore || !hasMore) return
    setLoadingMore(true)
    const res = await chatApi.directorySearch(botId, chatId, active.id, query.trim(), items.length)
    setLoadingMore(false)
    if (!res._ok || res.error) return
    setItems(prev => [...prev, ...(res.items || [])])
    setHasMore(Boolean(res.has_more))
  }

  function handleListScroll(e) {
    if (!active?.paginated || !hasMore || loading || loadingMore) return
    const el = e.currentTarget
    if (el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD_PX) loadMore()
  }

  return (
    <div className={`pc-dir ${open ? 'pc-dir--open' : ''}`}>
      <button
        type="button"
        className="pc-dir-handle"
        onClick={onToggle}
        title={open ? 'Cerrar directorio' : 'Abrir directorio'}
        aria-label={open ? 'Cerrar directorio' : 'Abrir directorio'}
      >
        <span className={`pc-dir-handle-arrow ${open ? 'pc-dir-handle-arrow--open' : ''}`}>›</span>
      </button>

      {sections.length > 1 && (
        <div className="pc-dir-tabs">
          {sections.map(s => (
            <button
              key={s.id}
              className={`pc-dir-tab ${s.id === activeId ? 'pc-dir-tab--active' : ''}`}
              onClick={() => setActiveId(s.id)}
            >
              {s.icon && <span className="pc-dir-tab-icon">{s.icon}</span>}
              <span className="pc-dir-tab-label">{s.label}</span>
            </button>
          ))}
        </div>
      )}

      {active && isConversations && (
        <ConversationsPanel
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={onSelectConversation}
          onNewConversation={onNewConversation}
        />
      )}

      {active && !isConversations && (
        <>
          <input
            className="pc-dir-search"
            type="text"
            value={query}
            placeholder={active.search_placeholder || `Buscar en ${active.label}…`}
            onChange={e => setQuery(e.target.value)}
          />

          <div className="pc-dir-list" ref={listRef} onScroll={handleListScroll}>
            {loading && <div className="pc-dir-status">Buscando…</div>}
            {!loading && error && <div className="pc-dir-status pc-dir-status--error">{error}</div>}
            {!loading && !error && active.empty_query === 'hide' && !query.trim() && (
              <div className="pc-dir-status">Escribí para buscar en {active.label.toLowerCase()}.</div>
            )}
            {!loading && !error && items.length === 0 && (query.trim() || active.empty_query === 'search') && (
              <div className="pc-dir-status">Sin resultados.</div>
            )}
            {!loading && items.map(item => (
              <ItemCard key={item.id} item={item} onOpen={active.mode === 'detail' ? setDetailItem : setConnectItem} />
            ))}
            {!loading && loadingMore && <div className="pc-dir-status">Cargando más…</div>}
          </div>
        </>
      )}

      {connectItem && active && (
        <ChatDirectoryConnect
          botId={botId}
          chatId={chatId}
          sectionId={active.id}
          item={connectItem}
          connectConfig={active.connect}
          onClose={() => setConnectItem(null)}
        />
      )}

      {detailItem && (
        <ChatDirectoryDetail item={detailItem} onClose={() => setDetailItem(null)} />
      )}
    </div>
  )
}
