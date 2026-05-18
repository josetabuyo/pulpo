import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy,
  useSortable, arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import WAScreenshotPanel from './WAScreenshotPanel'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(isoTs) {
  if (!isoTs) return ''
  const d = new Date(isoTs)
  return d.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })
}

function formatTime(isoTs) {
  if (!isoTs) return ''
  const d = new Date(isoTs)
  return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
}

function dayKey(isoTs) {
  return isoTs ? isoTs.slice(0, 10) : ''
}

function addSecond(isoTs) {
  if (!isoTs) return new Date().toISOString()
  try {
    return new Date(new Date(isoTs).getTime() + 1000).toISOString()
  } catch {
    return new Date().toISOString()
  }
}

// ─── Highlight helper ────────────────────────────────────────────────────────

function HighlightText({ text, query }) {
  if (!query || !text) return <>{text}</>
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === query.toLowerCase()
          ? <mark key={i} className="sv-highlight">{part}</mark>
          : part
      )}
    </>
  )
}

// ─── Burbujas (read-only) ─────────────────────────────────────────────────────

function ReplyQuote({ text }) {
  if (!text) return null
  const senderMatch = text.match(/^\[([^\]]+)\]\s*(.*)/)
  const sender = senderMatch ? senderMatch[1] : null
  const content = senderMatch ? senderMatch[2].trim() : text.trim()
  const isAudioDuration = /^\d{1,2}:\d{2}$/.test(content)
  const preview = isAudioDuration ? `🎵 audio ${content}` : content
  return (
    <div className="sv-reply-quote">
      <div className="sv-reply-quote-inner">
        {sender && <span className="sv-reply-sender">{sender}</span>}
        <span className="sv-reply-text">{preview || '↩'}</span>
      </div>
    </div>
  )
}

function TextBubble({ msg, highlight, dimmed }) {
  const isOut = msg.direction === 'out'
  return (
    <div
      className={`sv-bubble ${isOut ? 'sv-bubble--out' : 'sv-bubble--in'}`}
      style={dimmed ? { opacity: 0.25, transition: 'opacity 0.15s' } : undefined}
    >
      <div className="sv-bubble-body">
        {msg.sender && <span className="sv-bubble-sender">{msg.sender}</span>}
        <ReplyQuote text={msg.reply_to} />
        <p className="sv-bubble-text"><HighlightText text={msg.content} query={highlight} /></p>
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function AudioBubble({ msg, highlight, dimmed }) {
  const hasRealTranscription = msg.transcription && !msg.transcription.startsWith('[audio')
  const [expanded, setExpanded] = useState(hasRealTranscription)
  const isOut = msg.direction === 'out'
  return (
    <div
      className={`sv-bubble ${isOut ? 'sv-bubble--out' : 'sv-bubble--in'}`}
      style={dimmed ? { opacity: 0.25, transition: 'opacity 0.15s' } : undefined}
    >
      <div className="sv-bubble-body">
        {msg.sender && <span className="sv-bubble-sender">{msg.sender}</span>}
        <ReplyQuote text={msg.reply_to} />
        <div className="sv-audio-row">
          <span className="sv-audio-icon">🎵</span>
          <span className="sv-audio-duration">{msg.duration || 'audio'}</span>
          {hasRealTranscription && (
            <button className="sv-toggle-btn" onClick={() => setExpanded(e => !e)}>
              {expanded ? 'Ocultar' : 'Transcripción'}
            </button>
          )}
        </div>
        {expanded && hasRealTranscription && (
          <p className="sv-transcription"><HighlightText text={msg.transcription} query={highlight} /></p>
        )}
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function ImageBubble({ msg, apiCall, empresaId, contactPhone, dimmed }) {
  const isOut = msg.direction === 'out'
  const [blobUrl, setBlobUrl] = useState(null)
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    if (!msg.filename) return
    let objectUrl = null
    let cancelled = false
    const path = `/summarizer/${empresaId}/${contactPhone}/docs/${encodeURIComponent(msg.filename)}`
    apiCall('GET_BLOB', path, null)
      .then(blob => {
        if (cancelled || !blob || blob.size === 0) return
        objectUrl = URL.createObjectURL(blob)
        setBlobUrl(objectUrl)
      })
      .catch(() => {})
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setBlobUrl(null)
    }
  }, [msg.filename, empresaId, contactPhone]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div
        className={`sv-bubble ${isOut ? 'sv-bubble--out' : 'sv-bubble--in'}`}
        style={dimmed ? { opacity: 0.25, transition: 'opacity 0.15s' } : undefined}
      >
        <div className="sv-bubble-body">
          {msg.sender && <span className="sv-bubble-sender">{msg.sender}</span>}
          <ReplyQuote text={msg.reply_to} />
          <div
            className={`sv-img-row${blobUrl ? ' sv-img-row--loaded' : ''}`}
            onClick={blobUrl ? () => setModalOpen(true) : undefined}
            style={{ cursor: blobUrl ? 'pointer' : 'default' }}
            title={blobUrl ? 'Click para ampliar' : undefined}
          >
            {blobUrl ? (
              <img src={blobUrl} alt={msg.filename || 'imagen'} className="sv-img-thumb" />
            ) : (
              <>
                <span className="sv-img-icon">🖼</span>
                <span className="sv-img-name">{msg.filename || 'imagen'}</span>
              </>
            )}
          </div>
          {msg.caption && <p className="sv-bubble-text sv-img-caption">{msg.caption}</p>}
          <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
        </div>
      </div>
      {modalOpen && blobUrl && (
        <div className="sv-img-modal" onClick={() => setModalOpen(false)}>
          <img src={blobUrl} alt={msg.filename || 'imagen'} className="sv-img-modal-img" />
        </div>
      )}
    </>
  )
}

function DocumentBubble({ msg, apiCall, empresaId, contactPhone, dimmed }) {
  function handleDownload(e) {
    e.preventDefault()
    const url = `/summarizer/${empresaId}/${contactPhone}/docs/${encodeURIComponent(msg.filename)}`
    apiCall('GET_BLOB', url, null).then(blob => {
      if (!blob) return
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = msg.filename
      a.click()
      URL.revokeObjectURL(a.href)
    }).catch(() => { window.open('/api' + url, '_blank') })
  }
  return (
    <div
      className="sv-bubble sv-bubble--in"
      style={dimmed ? { opacity: 0.25, transition: 'opacity 0.15s' } : undefined}
    >
      <div className="sv-bubble-body">
        <div className="sv-doc-row">
          <span className="sv-doc-icon">📄</span>
          <div className="sv-doc-info">
            <span className="sv-doc-name">{msg.filename}</span>
            {msg.size && <span className="sv-doc-size">{msg.size}</span>}
          </div>
          <button className="sv-download-btn" onClick={handleDownload}>↓ Descargar</button>
        </div>
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function DaySeparator({ label }) {
  return (
    <div className="sv-day-sep">
      <span className="sv-day-sep-label">{label}</span>
    </div>
  )
}

// ─── Stats bar ────────────────────────────────────────────────────────────────

function statsText(messages) {
  if (!messages || messages.length === 0) return null
  const total  = messages.length
  const audios = messages.filter(m => m.type === 'audio').length
  const images = messages.filter(m => m.type === 'image').length
  const docs   = messages.filter(m => m.type === 'document').length
  const withTs = messages.filter(m => m.timestamp)
  const first  = withTs.length ? withTs[0].timestamp.slice(0, 10) : null
  const last   = withTs.length ? withTs[withTs.length - 1].timestamp.slice(0, 10) : null
  const range  = first && last ? (first === last ? first : `${first} → ${last}`) : null
  const parts  = [`${total} mensajes`]
  if (audios) parts.push(`${audios} audios`)
  if (images) parts.push(`${images} imágenes`)
  if (docs)   parts.push(`${docs} docs`)
  if (range)  parts.push(range)
  return parts.join('  ·  ')
}

// ─── Sortable bubble (tuning mode) ───────────────────────────────────────────

function SortableBubble({ msg, onDelete, apiCall, empresaId, contactPhone, highlight, dimmed }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: msg._id || msg._localId })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  function renderContent() {
    if (msg.type === 'audio') return <AudioBubble msg={msg} highlight={highlight} dimmed={dimmed} />
    if (msg.type === 'image') return <ImageBubble msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} dimmed={dimmed} />
    if (msg.type === 'document') return <DocumentBubble msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} dimmed={dimmed} />
    return <TextBubble msg={msg} highlight={highlight} dimmed={dimmed} />
  }

  return (
    <div ref={setNodeRef} style={style} className="sv-tuning-row">
      <div className="sv-tuning-bubble-wrap">
        <span className="sv-drag-handle" {...attributes} {...listeners}>⠿</span>
        <div className="sv-tuning-bubble-area">
          {renderContent()}
        </div>
        <button className="sv-delete-btn" onClick={() => onDelete(msg)} title="Eliminar">×</button>
      </div>
    </div>
  )
}

// ─── Insert form ──────────────────────────────────────────────────────────────

function InsertForm({ senders, onConfirm, onCancel }) {
  const [sender, setSender] = useState('')
  const [content, setContent] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!content.trim()) return
    onConfirm({ sender: sender || null, content: content.trim(), timestamp: null, type: 'text' })
  }

  return (
    <form className="sv-insert-form" onSubmit={handleSubmit}>
      <input
        list="sv-senders-list"
        placeholder="Sender (opcional)"
        value={sender}
        onChange={e => setSender(e.target.value)}
        className="sv-insert-sender"
      />
      <datalist id="sv-senders-list">
        {senders.map(s => <option key={s} value={s} />)}
      </datalist>
      <textarea
        placeholder="Contenido del mensaje"
        value={content}
        onChange={e => setContent(e.target.value)}
        className="sv-insert-content"
        rows={2}
        autoFocus
      />
      <div className="sv-insert-actions">
        <button type="submit" className="sv-insert-ok">Agregar</button>
        <button type="button" className="sv-insert-cancel" onClick={onCancel}>Cancelar</button>
      </div>
    </form>
  )
}

// ─── SummaryView ──────────────────────────────────────────────────────────────

export default function SummaryView({ empresaId, contactPhone, contactName, apiCall, onBack }) {
  const [messages, setMessages]     = useState(null)
  const [error, setError]           = useState(null)
  const [syncing, setSyncing]       = useState(false)
  const messagesRef                 = useRef(null)

  // Search state
  const [searchQuery, setSearchQuery]     = useState('')

  // Tuning state
  const [tuningMode, setTuningMode]       = useState(false)
  const [editMessages, setEditMessages]   = useState(null)
  const editMessagesRef                   = useRef(null)
  const [history, setHistory]             = useState([])
  const [historyIdx, setHistoryIdx]       = useState(-1)
  const [consolidation, setConsolidation] = useState(null)
  const [insertForm, setInsertForm]       = useState(null)  // { afterMsg } | null
  const [saveStatus, setSaveStatus]       = useState(null)  // 'saving' | 'ok' | 'error'
  const saveStatusTimer                   = useRef(null)
  const currentVersion                    = useRef(null)    // mtime del chat.md al entrar a tuning

  function log(msg) {
    console.log('[tuning]', msg)
  }

  function notifySave(status) {
    if (saveStatusTimer.current) clearTimeout(saveStatusTimer.current)
    setSaveStatus(status)
    if (status !== 'saving') {
      saveStatusTimer.current = setTimeout(() => setSaveStatus(null), 3000)
    }
  }

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  // ── carga mensajes (read-only path) ────────────────────────────────────────

  function loadMessages() {
    setMessages(null)
    setError(null)
    apiCall('GET', `/summarizer/${empresaId}/${contactPhone}/messages`, null)
      .then(data => {
        if (data?.messages) setMessages(data.messages)
        else setError('Sin mensajes')
      })
      .catch(() => setError('Error al cargar'))
  }

  // carga mensajes con IDs para el tuning
  function loadEditMessages() {
    return apiCall('GET', `/summarizer/${empresaId}/${contactPhone}/messages?include_ids=true`, null)
      .then(data => {
        if (data?.version != null) currentVersion.current = data.version
        return data?.messages || []
      })
  }

  useEffect(() => { loadMessages() }, [empresaId, contactPhone])

  useEffect(() => {
    if (messages && messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [messages])

  // ── helpers ──────────────────────────────────────────────────────────────────

  function withLocalIds(msgs) {
    return msgs.map((m, i) => ({ ...m, _localId: m._id || `local-${i}` }))
  }

  function pushSnapshot(msgs) {
    setHistory(prev => {
      const newHist = prev.slice(0, historyIdx + 1).concat([msgs]).slice(-30)
      setHistoryIdx(newHist.length - 1)
      return newHist
    })
    editMessagesRef.current = msgs
    setEditMessages(msgs)
  }

  async function putMessages(msgs) {
    log(`PUT /messages → enviando ${msgs.length} msgs (version=${currentVersion.current})`)
    notifySave('saving')
    try {
      const payload = { messages: msgs }
      if (currentVersion.current != null) payload.version = currentVersion.current
      const res = await apiCall('PUT', `/summarizer/${empresaId}/${contactPhone}/messages`, payload)
      if (res?._status === 409) {
        log('PUT /messages ← 409 Conflict — recargando')
        notifySave('error')
        const fresh = withLocalIds(await loadEditMessages())
        pushSnapshot(fresh)
        alert('Otro proceso modificó el resumen. Se recargaron los datos más recientes.')
        return null
      }
      if (res?.ok) {
        currentVersion.current = res.version ?? currentVersion.current
        log(`PUT /messages ← ok count=${res?.message_count ?? '?'} version=${res?.version}`)
        notifySave('ok')
      } else {
        log(`PUT /messages ← respuesta inesperada: ${JSON.stringify(res)}`)
        notifySave('error')
      }
      return res
    } catch (err) {
      log(`PUT /messages ← ERROR: ${err}`)
      notifySave('error')
      throw err
    }
  }

  async function reloadAndSnapshot() {
    log('reloadAndSnapshot → GET /messages inbound_only')
    const fresh = await loadEditMessages()
    log(`reloadAndSnapshot ← ${fresh.length} msgs. IDs: [${fresh.slice(0,5).map(m=>m._id).join(',')}${fresh.length>5?'...':''}]`)
    const msgs = withLocalIds(fresh)
    pushSnapshot(msgs)
  }

  // ── tuning mode toggle ──────────────────────────────────────────────────────

  async function activateTuning() {
    log('activateTuning → cargando mensajes inbound_only')
    const msgs = await loadEditMessages()
    log(`activateTuning ← ${msgs.length} msgs. IDs: [${msgs.slice(0,5).map(m=>m._id).join(',')}${msgs.length>5?'...':''}]`)
    const withLocal = withLocalIds(msgs)
    editMessagesRef.current = withLocal
    setEditMessages(withLocal)
    setHistory([withLocal])
    setHistoryIdx(0)
    setTuningMode(true)
    if (contactName) {
      apiCall('POST', `/summarizer/${empresaId}/wa-open-chat`, { contact_name: contactName }).catch(() => {})
    }
    apiCall('GET', `/summarizer/${empresaId}/${contactPhone}/consolidation`, null)
      .then(meta => setConsolidation(meta))
      .catch(() => setConsolidation(null))
  }

  function deactivateTuning() {
    setTuningMode(false)
    setInsertForm(null)
    loadMessages()
  }

  // ── undo / redo ─────────────────────────────────────────────────────────────

  async function handleUndo() {
    if (historyIdx <= 0) return
    const newIdx = historyIdx - 1
    log(`undo historyIdx ${historyIdx}→${newIdx}, restaurando ${history[newIdx]?.length} msgs`)
    const msgs = history[newIdx]
    setHistoryIdx(newIdx)
    setEditMessages(msgs)
    await putMessages(msgs)
    const fresh = withLocalIds(await loadEditMessages())
    setEditMessages(fresh)
  }

  async function handleRedo() {
    if (historyIdx >= history.length - 1) return
    const newIdx = historyIdx + 1
    log(`redo historyIdx ${historyIdx}→${newIdx}, restaurando ${history[newIdx]?.length} msgs`)
    const msgs = history[newIdx]
    setHistoryIdx(newIdx)
    setEditMessages(msgs)
    await putMessages(msgs)
    const fresh = withLocalIds(await loadEditMessages())
    setEditMessages(fresh)
  }

  // ── drag & drop ─────────────────────────────────────────────────────────────

  async function handleDragEnd(event) {
    const { active, over } = event
    log(`dragEnd active=${active?.id} over=${over?.id}`)
    if (!over) { log('dragEnd → over=null, abortando'); return }
    if (active.id === over.id) { log('dragEnd → mismo elemento, abortando'); return }
    const oldIdx = editMessages.findIndex(m => (m._id || m._localId) === active.id)
    const newIdx = editMessages.findIndex(m => (m._id || m._localId) === over.id)
    log(`dragEnd → oldIdx=${oldIdx} newIdx=${newIdx} totalMsgs=${editMessages.length}`)
    if (oldIdx === -1 || newIdx === -1) {
      log(`dragEnd → índice no encontrado (oldIdx=${oldIdx} newIdx=${newIdx}), abortando`)
      return
    }
    const reordered = arrayMove(editMessages, oldIdx, newIdx)
    log(`dragEnd → reordered[0].id=${reordered[0]?._id} reordered[${reordered.length-1}].id=${reordered[reordered.length-1]?._id}`)
    setEditMessages(reordered) // optimistic
    await putMessages(reordered)
    await reloadAndSnapshot() // IDs frescos del server
  }

  // ── delete ──────────────────────────────────────────────────────────────────

  async function handleDelete(msg) {
    log(`delete msg _id=${msg._id} _localId=${msg._localId} type=${msg.type}`)
    const filtered = editMessages.filter(m => (m._id || m._localId) !== (msg._id || msg._localId))
    log(`delete → de ${editMessages.length} a ${filtered.length} msgs`)
    setEditMessages(filtered) // optimistic
    await putMessages(filtered)
    await reloadAndSnapshot()
  }

  // ── insert ──────────────────────────────────────────────────────────────────

  function getLastVisibleIndex() {
    if (!messagesRef.current || !editMessages?.length) return (editMessages?.length ?? 1) - 1
    const container = messagesRef.current
    const containerRect = container.getBoundingClientRect()
    const rows = container.querySelectorAll('.sv-tuning-row')
    let lastVisible = editMessages.length - 1
    rows.forEach((row, i) => {
      if (row.getBoundingClientRect().top < containerRect.bottom) lastVisible = i
    })
    return lastVisible
  }

  async function handleInsertConfirm(data) {
    const insertAfterIdx = insertForm?.insertAfterIdx ?? (editMessagesRef.current?.length ?? 0) - 1
    setInsertForm(null)
    const current = editMessagesRef.current || []
    const newMsg = {
      type: data.type || 'text',
      content: data.content,
      sender: data.sender || null,
      timestamp: data.timestamp || null,
      direction: 'in',
      _localId: `local-insert-${Date.now()}`,
    }
    const insertAt = Math.min(insertAfterIdx + 1, current.length)
    const next = [
      ...current.slice(0, insertAt),
      newMsg,
      ...current.slice(insertAt),
    ]
    editMessagesRef.current = next
    setEditMessages(next)
    await putMessages(next)
    await reloadAndSnapshot()
  }

  // ── consolidar ──────────────────────────────────────────────────────────────

  async function handleConsolidate() {
    const lastDate = editMessages?.length
      ? formatDate(editMessages[editMessages.length - 1].timestamp)
      : '?'
    if (!window.confirm(`Consolidar resumen hasta ${lastDate}. ¿Continuar?`)) return
    const meta = await apiCall('POST', `/summarizer/${empresaId}/${contactPhone}/consolidate`, {})
    setConsolidation(meta)
  }

  // ── sync / full-resync ──────────────────────────────────────────────────────

  async function handleSync() {
    setSyncing(true)
    try {
      await apiCall('POST', `/summarizer/${empresaId}/${contactPhone}/sync`, {})
      loadMessages()
    } catch {
      setError('Error al sincronizar')
    } finally {
      setSyncing(false)
    }
  }

  async function handleFullResync() {
    let msg = '¿Borrar todo el historial local y re-scrapear desde WA Web? Esto puede tardar varios minutos.'
    if (consolidation?.last_message_ts) {
      const d = new Date(consolidation.last_message_ts).toLocaleDateString('es-AR')
      msg = `Re-scrape desde ${d} (consolidación). ¿Continuar?`
    }
    if (!window.confirm(msg)) return
    setSyncing(true)
    const body = consolidation?.last_message_ts
      ? { from_date: consolidation.last_message_ts }
      : {}
    try {
      await apiCall('POST', `/summarizer/${empresaId}/${contactPhone}/full-resync`, body)
      loadMessages()
    } catch {
      setError('Error en full re-sync')
    } finally {
      setSyncing(false)
    }
  }

  function handleDownloadMd() {
    apiCall('GET_TEXT', `/summarizer/${empresaId}/${contactPhone}`, null).then(text => {
      if (!text) return
      const blob = new Blob([text], { type: 'text/markdown' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `resumen_${contactPhone}.md`
      a.click()
      URL.revokeObjectURL(a.href)
    })
  }

  // ── senders únicos para el datalist ─────────────────────────────────────────

  const uniqueSenders = [...new Set(
    (editMessages || []).map(m => m.sender).filter(Boolean)
  )]

  // ── renderizado de burbujas (read-only) ─────────────────────────────────────

  const items = []
  if (messages) {
    let lastDay = null
    for (const msg of messages) {
      const day = dayKey(msg.timestamp)
      if (day && day !== lastDay) {
        items.push({ kind: 'sep', day, label: formatDate(msg.timestamp) })
        lastDay = day
      }
      items.push({ kind: 'msg', msg })
    }
  }

  // ── IDs para DnD (el contexto necesita array de IDs) ────────────────────────

  const dndIds = (editMessages || []).map(m => m._id || m._localId)

  // ── Search match count ───────────────────────────────────────────────────────

  const searchMatchCount = useMemo(() => {
    if (!searchQuery || !messages) return 0
    const q = searchQuery.toLowerCase()
    return messages.filter(m =>
      (m.content && m.content.toLowerCase().includes(q)) ||
      (m.transcription && m.transcription.toLowerCase().includes(q))
    ).length
  }, [searchQuery, messages])

  // ── render ──────────────────────────────────────────────────────────────────

  return (
    <div className={`sv-container ${tuningMode ? 'sv-container--tuning' : ''}`}>

      {/* Header */}
      <div className="sv-header">
        <button className="sv-back-btn" onClick={onBack}>← Volver</button>
        <div className="sv-header-info">
          <span className="sv-contact-name">{contactName || contactPhone}</span>
          <span className="sv-contact-phone">{contactPhone}</span>
        </div>

        {consolidation && (
          <span className="sv-consolidation-badge" title={`Consolidado: ${consolidation.consolidated_at}`}>
            ✓ hasta {new Date(consolidation.last_message_ts || consolidation.consolidated_at).toLocaleDateString('es-AR')}
          </span>
        )}

        {tuningMode && saveStatus && (
          <span className={`sv-save-status sv-save-status--${saveStatus}`}>
            {saveStatus === 'saving' ? '...' : saveStatus === 'ok' ? '✓ Guardado' : '✗ Error al guardar'}
          </span>
        )}

        {tuningMode ? (
          <>
            <button
              className="sv-md-btn sv-md-btn--active"
              onClick={deactivateTuning}
              title="Salir del modo tuning"
            >✏ Tuning ON</button>
            <button
              className="sv-md-btn"
              onClick={handleUndo}
              disabled={historyIdx <= 0}
              title="Deshacer"
            >↩ Undo</button>
            <button
              className="sv-md-btn"
              onClick={handleRedo}
              disabled={historyIdx >= history.length - 1}
              title="Rehacer"
            >↪ Redo</button>
            <button
              className="sv-md-btn sv-md-btn--primary"
              onClick={handleConsolidate}
              title="Consolidar resumen"
            >✓ Consolidar</button>
          </>
        ) : (
          <>
            <button className="sv-md-btn sv-md-btn--tuning" onClick={activateTuning} title="Activar modo edición">
              ✏ Tuning
            </button>
            <button className="sv-md-btn" onClick={handleSync} disabled={syncing} title="Delta sync desde historial WA">
              {syncing ? '...' : '↻'}
            </button>
            <button className="sv-md-btn sv-md-btn--danger" onClick={handleFullResync} disabled={syncing} title="Full re-sync">
              {syncing ? '...' : '⟳ Full'}
            </button>
            <button className="sv-md-btn" onClick={handleDownloadMd} title="Descargar resumen completo">
              ↓ MD
            </button>
          </>
        )}
      </div>

      {/* Stats */}
      {messages?.length > 0 && (
        <div className="sv-stats-bar">
          <div className="sv-search-wrap">
            <input
              className="sv-search-input"
              type="text"
              placeholder="Buscar…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <span className="sv-search-count">
                {searchMatchCount === 0 ? 'sin resultados' : `${searchMatchCount} resultado${searchMatchCount !== 1 ? 's' : ''}`}
              </span>
            )}
            {searchQuery && (
              <button className="sv-search-clear" onClick={() => setSearchQuery('')} title="Limpiar">×</button>
            )}
          </div>
          <span className="sv-stats-text">{statsText(messages)}</span>
        </div>
      )}

      {/* Layout tuning: dos columnas */}
      {tuningMode ? (
        <div className="sv-tuning-layout">

          {/* Panel izquierdo: mensajes editables */}
          <div className="sv-tuning-left">
            <div className="sv-tuning-messages" ref={messagesRef}>
              {!editMessages && <div className="sv-loading">Cargando...</div>}
              {editMessages && editMessages.length === 0 && (
                <div className="sv-empty">Sin mensajes</div>
              )}

              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={dndIds} strategy={verticalListSortingStrategy}>
                  {(editMessages || []).map((msg) => {
                    const q = searchQuery.toLowerCase()
                    const matches = !searchQuery || (
                      (msg.content && msg.content.toLowerCase().includes(q)) ||
                      (msg.transcription && msg.transcription.toLowerCase().includes(q))
                    )
                    return (
                      <SortableBubble
                        key={msg._id || msg._localId}
                        msg={msg}
                        onDelete={handleDelete}
                        apiCall={apiCall}
                        empresaId={empresaId}
                        contactPhone={contactPhone}
                        highlight={searchQuery}
                        dimmed={!matches}
                      />
                    )
                  })}
                </SortableContext>
              </DndContext>
            </div>

            <div className="sv-tuning-footer">
              {insertForm ? (
                <InsertForm
                  senders={uniqueSenders}
                  onConfirm={handleInsertConfirm}
                  onCancel={() => setInsertForm(null)}
                />
              ) : (
                <button
                  className="sv-add-end-btn"
                  onClick={() => setInsertForm({ insertAfterIdx: getLastVisibleIndex() })}
                >
                  + Agregar mensaje
                </button>
              )}
            </div>
          </div>

          {/* Panel derecho: screenshot WA */}
          <div className="sv-tuning-screenshot">
            <WAScreenshotPanel empresaId={empresaId} apiCall={apiCall} active={tuningMode} />
          </div>
        </div>
      ) : (
        /* Layout normal: lista de mensajes */
        <div className="sv-messages" ref={messagesRef}>
          {!messages && !error && <div className="sv-loading">Cargando...</div>}
          {error && <div className="sv-empty">{error}</div>}
          {messages && messages.length === 0 && (
            <div className="sv-empty">Sin mensajes acumulados</div>
          )}
          {items.map((item, i) => {
            if (item.kind === 'sep') {
              return <DaySeparator key={`sep-${item.day}`} label={item.label} />
            }
            const { msg } = item
            const q = searchQuery.toLowerCase()
            const matches = !searchQuery || (
              (msg.content && msg.content.toLowerCase().includes(q)) ||
              (msg.transcription && msg.transcription.toLowerCase().includes(q))
            )
            const dimmed = !matches
            if (msg.type === 'audio') return (
              <AudioBubble key={i} msg={msg} highlight={searchQuery} dimmed={dimmed} />
            )
            if (msg.type === 'image') return (
              <ImageBubble key={i} msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} dimmed={dimmed} />
            )
            if (msg.type === 'document') return (
              <DocumentBubble key={i} msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} dimmed={dimmed} />
            )
            return <TextBubble key={i} msg={msg} highlight={searchQuery} dimmed={dimmed} />
          })}
        </div>
      )}
    </div>
  )
}
