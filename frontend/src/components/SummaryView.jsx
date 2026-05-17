import { useState, useEffect, useRef, useCallback } from 'react'
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

function TextBubble({ msg }) {
  const isOut = msg.direction === 'out'
  return (
    <div className={`sv-bubble ${isOut ? 'sv-bubble--out' : 'sv-bubble--in'}`}>
      <div className="sv-bubble-body">
        {msg.sender && <span className="sv-bubble-sender">{msg.sender}</span>}
        <ReplyQuote text={msg.reply_to} />
        <p className="sv-bubble-text">{msg.content}</p>
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function AudioBubble({ msg }) {
  const hasRealTranscription = msg.transcription && !msg.transcription.startsWith('[audio')
  const [expanded, setExpanded] = useState(hasRealTranscription)
  const isOut = msg.direction === 'out'
  return (
    <div className={`sv-bubble ${isOut ? 'sv-bubble--out' : 'sv-bubble--in'}`}>
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
          <p className="sv-transcription">{msg.transcription}</p>
        )}
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function ImageBubble({ msg, apiCall, empresaId, contactPhone }) {
  const isOut = msg.direction === 'out'
  function handleView() {
    if (!msg.filename) return
    const url = `/summarizer/${empresaId}/${contactPhone}/docs/${encodeURIComponent(msg.filename)}`
    apiCall('GET_BLOB', url, null).then(blob => {
      if (!blob) return
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.target = '_blank'
      a.rel = 'noopener'
      a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 10000)
    }).catch(() => {})
  }
  return (
    <div className={`sv-bubble ${isOut ? 'sv-bubble--out' : 'sv-bubble--in'}`}>
      <div className="sv-bubble-body">
        {msg.sender && <span className="sv-bubble-sender">{msg.sender}</span>}
        <ReplyQuote text={msg.reply_to} />
        <div
          className="sv-img-row"
          onClick={msg.filename ? handleView : undefined}
          style={{ cursor: msg.filename ? 'pointer' : 'default' }}
          title={msg.filename ? 'Click para ver imagen' : undefined}
        >
          <span className="sv-img-icon">🖼</span>
          <span className="sv-img-name">{msg.filename || 'imagen'}</span>
        </div>
        {msg.caption && <p className="sv-bubble-text sv-img-caption">{msg.caption}</p>}
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function DocumentBubble({ msg, apiCall, empresaId, contactPhone }) {
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
    <div className="sv-bubble sv-bubble--in">
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

function StatsBar({ messages }) {
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
  return <div className="sv-stats-bar">{parts.join('  ·  ')}</div>
}

// ─── Sortable bubble (tuning mode) ───────────────────────────────────────────

function SortableBubble({ msg, onDelete, onInsertAfter, apiCall, empresaId, contactPhone }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: msg._id || msg._localId })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  function renderContent() {
    if (msg.type === 'audio') return <AudioBubble msg={msg} />
    if (msg.type === 'image') return <ImageBubble msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} />
    if (msg.type === 'document') return <DocumentBubble msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} />
    return <TextBubble msg={msg} />
  }

  return (
    <div ref={setNodeRef} style={style} className="sv-tuning-row">
      <span className="sv-drag-handle" {...attributes} {...listeners}>⠿</span>
      <div className="sv-tuning-bubble-wrap">
        {renderContent()}
        <button
          className="sv-delete-btn"
          onClick={() => onDelete(msg)}
          title="Eliminar mensaje"
        >×</button>
      </div>
      <button className="sv-insert-after-btn" onClick={() => onInsertAfter(msg)}>
        + insertar aquí
      </button>
    </div>
  )
}

// ─── Insert form ──────────────────────────────────────────────────────────────

function InsertForm({ afterMsg, senders, onConfirm, onCancel }) {
  const [sender, setSender] = useState('')
  const [content, setContent] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!content.trim()) return
    const ts = afterMsg ? addSecond(afterMsg.timestamp) : new Date().toISOString()
    onConfirm({ sender: sender || null, content: content.trim(), timestamp: ts, type: 'text' })
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

  // Tuning state
  const [tuningMode, setTuningMode]       = useState(false)
  const [editMessages, setEditMessages]   = useState(null)
  const [history, setHistory]             = useState([])
  const [historyIdx, setHistoryIdx]       = useState(-1)
  const [consolidation, setConsolidation] = useState(null)
  const [insertForm, setInsertForm]       = useState(null)  // { afterMsg } | null

  const sensors = useSensors(useSensor(PointerSensor))

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
      .then(data => data?.messages || [])
  }

  useEffect(() => { loadMessages() }, [empresaId, contactPhone])

  useEffect(() => {
    if (messages && messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [messages])

  // ── snapshot helpers ────────────────────────────────────────────────────────

  function pushSnapshot(msgs) {
    setHistory(prev => {
      const newHist = prev.slice(0, historyIdx + 1).concat([msgs]).slice(-30)
      setHistoryIdx(newHist.length - 1)
      return newHist
    })
    setEditMessages(msgs)
  }

  async function putMessages(msgs) {
    await apiCall('PUT', `/summarizer/${empresaId}/${contactPhone}/messages`, { messages: msgs })
  }

  // ── tuning mode toggle ──────────────────────────────────────────────────────

  async function activateTuning() {
    const msgs = await loadEditMessages()
    // Asignar _localId para DnD (fallback cuando _id es null)
    const withLocal = msgs.map((m, i) => ({ ...m, _localId: m._id || `local-${i}` }))
    setEditMessages(withLocal)
    setHistory([withLocal])
    setHistoryIdx(0)
    setTuningMode(true)
    // Cargar estado de consolidación
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
    const msgs = history[newIdx]
    setHistoryIdx(newIdx)
    setEditMessages(msgs)
    await putMessages(msgs)
  }

  async function handleRedo() {
    if (historyIdx >= history.length - 1) return
    const newIdx = historyIdx + 1
    const msgs = history[newIdx]
    setHistoryIdx(newIdx)
    setEditMessages(msgs)
    await putMessages(msgs)
  }

  // ── drag & drop ─────────────────────────────────────────────────────────────

  async function handleDragEnd(event) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIdx = editMessages.findIndex(m => (m._id || m._localId) === active.id)
    const newIdx = editMessages.findIndex(m => (m._id || m._localId) === over.id)
    if (oldIdx === -1 || newIdx === -1) return
    const reordered = arrayMove(editMessages, oldIdx, newIdx)
    pushSnapshot(reordered)
    await putMessages(reordered)
  }

  // ── delete ──────────────────────────────────────────────────────────────────

  async function handleDelete(msg) {
    if (msg._id) {
      await apiCall('DELETE', `/summarizer/${empresaId}/${contactPhone}/message/${msg._id}`, null)
    }
    const updated = editMessages.filter(m => (m._id || m._localId) !== (msg._id || msg._localId))
    pushSnapshot(updated)
  }

  // ── insert ──────────────────────────────────────────────────────────────────

  function handleInsertAfter(msg) {
    setInsertForm({ afterMsg: msg })
  }

  function handleInsertAtEnd() {
    setInsertForm({ afterMsg: editMessages?.[editMessages.length - 1] || null })
  }

  async function handleInsertConfirm(data) {
    setInsertForm(null)
    await apiCall('POST', `/summarizer/${empresaId}/${contactPhone}/message`, data)
    const fresh = await loadEditMessages()
    const withLocal = fresh.map((m, i) => ({ ...m, _localId: m._id || `local-${i}` }))
    pushSnapshot(withLocal)
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
      <StatsBar messages={tuningMode ? editMessages : messages} />

      {/* Layout tuning: dos columnas */}
      {tuningMode ? (
        <div className="sv-tuning-layout">

          {/* Panel izquierdo: mensajes editables */}
          <div className="sv-tuning-messages" ref={messagesRef}>
            {!editMessages && <div className="sv-loading">Cargando...</div>}
            {editMessages && editMessages.length === 0 && (
              <div className="sv-empty">Sin mensajes</div>
            )}

            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={dndIds} strategy={verticalListSortingStrategy}>
                {(editMessages || []).map((msg) => (
                  <div key={msg._id || msg._localId}>
                    <SortableBubble
                      msg={msg}
                      onDelete={handleDelete}
                      onInsertAfter={handleInsertAfter}
                      apiCall={apiCall}
                      empresaId={empresaId}
                      contactPhone={contactPhone}
                    />
                    {insertForm?.afterMsg?._id === msg._id && (
                      <InsertForm
                        afterMsg={msg}
                        senders={uniqueSenders}
                        onConfirm={handleInsertConfirm}
                        onCancel={() => setInsertForm(null)}
                      />
                    )}
                  </div>
                ))}
              </SortableContext>
            </DndContext>

            {/* Insertar al final */}
            {insertForm && !insertForm.afterMsg?._id && (
              <InsertForm
                afterMsg={insertForm.afterMsg}
                senders={uniqueSenders}
                onConfirm={handleInsertConfirm}
                onCancel={() => setInsertForm(null)}
              />
            )}
            <button className="sv-add-end-btn" onClick={handleInsertAtEnd}>
              + Agregar mensaje al final
            </button>
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
            if (msg.type === 'audio') return <AudioBubble key={i} msg={msg} />
            if (msg.type === 'image') return (
              <ImageBubble key={i} msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} />
            )
            if (msg.type === 'document') return (
              <DocumentBubble key={i} msg={msg} apiCall={apiCall} empresaId={empresaId} contactPhone={contactPhone} />
            )
            return <TextBubble key={i} msg={msg} />
          })}
        </div>
      )}
    </div>
  )
}
