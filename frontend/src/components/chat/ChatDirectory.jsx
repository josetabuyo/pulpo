import { useEffect, useRef, useState } from 'react'
import { chatApi } from '../../lib/chatApi.js'
import ChatDirectoryConnect from './ChatDirectoryConnect.jsx'
import ChatDirectoryDetail from './ChatDirectoryDetail.jsx'

const DEBOUNCE_MS = 300

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

/**
 * Rail izquierdo, camino paralelo al chat conversacional: buscador +
 * lista por sección configurable (comercios/servicios/noticias, ver
 * web/lib/business/chat-directory-types.ts). Cada sección define su propio
 * `mode`: "connect" (default) dispara el mismo tipo de lead que hoy arma el
 * nodo HTTP del flow al tocar un item; "detail" abre una vista de solo
 * lectura con link a la fuente original, sin form ni lead -- pensado para
 * listas tipo noticias. Genérico: nada acá conoce a Luganense ni a ningún
 * bot en particular, todo sale de la config guardada en `chat_configs.directory`.
 */
export default function ChatDirectory({ botId, chatId, directory, open, onClose }) {
  const sections = directory?.sections || []
  const [activeId, setActiveId] = useState(sections[0]?.id || null)
  const [query, setQuery] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [connectItem, setConnectItem] = useState(null)
  const [detailItem, setDetailItem] = useState(null)

  const debounceRef = useRef(null)
  const active = sections.find(s => s.id === activeId) || sections[0] || null

  useEffect(() => {
    if (!activeId && sections[0]) setActiveId(sections[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sections])

  useEffect(() => {
    setQuery('')
    setItems([])
    setError('')
  }, [activeId])

  useEffect(() => {
    if (!active) return
    const trimmed = query.trim()
    const minLen = active.min_query_len ?? 0
    const shouldSearch = active.empty_query === 'hide' ? trimmed.length > 0 : trimmed.length >= minLen
    if (!shouldSearch) { setItems([]); return }

    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      setError('')
      const res = await chatApi.directorySearch(botId, chatId, active.id, trimmed)
      setLoading(false)
      if (!res._ok) { setError('No se pudo buscar. Probá de nuevo.'); return }
      if (res.error) { setError(res.error); return }
      setItems(res.items || [])
    }, DEBOUNCE_MS)

    return () => clearTimeout(debounceRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, active, botId, chatId])

  if (!directory?.enabled || sections.length === 0) return null

  return (
    <div className={`pc-dir ${open ? 'pc-dir--open' : ''}`}>
      <div className="pc-dir-title">{directory.title || 'Directorio'}</div>

      {sections.length > 1 && (
        <div className="pc-dir-tabs">
          {sections.map(s => (
            <button
              key={s.id}
              className={`pc-dir-tab ${s.id === activeId ? 'pc-dir-tab--active' : ''}`}
              onClick={() => setActiveId(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      {active && (
        <>
          <input
            className="pc-dir-search"
            type="text"
            value={query}
            placeholder={active.search_placeholder || `Buscar en ${active.label}…`}
            onChange={e => setQuery(e.target.value)}
          />

          <div className="pc-dir-list">
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
          </div>
        </>
      )}

      {open && <button className="pc-dir-close-mobile" onClick={onClose}>Cerrar</button>}

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
