import { useState, useEffect, useRef } from 'react'

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

// ─── Burbujas ─────────────────────────────────────────────────────────────────

function TextBubble({ msg }) {
  return (
    <div className="sv-bubble sv-bubble--in">
      <div className="sv-bubble-body">
        <p className="sv-bubble-text">{msg.content}</p>
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function AudioBubble({ msg }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="sv-bubble sv-bubble--in">
      <div className="sv-bubble-body">
        <div className="sv-audio-row">
          <span className="sv-audio-icon">🎵</span>
          <span className="sv-audio-duration">{msg.duration || 'audio'}</span>
          {msg.transcription && (
            <button
              className="sv-toggle-btn"
              onClick={() => setExpanded(e => !e)}
            >
              {expanded ? 'Ocultar' : 'Transcripción'}
            </button>
          )}
        </div>
        {expanded && msg.transcription && (
          <p className="sv-transcription">{msg.transcription}</p>
        )}
        <span className="sv-bubble-time">{formatTime(msg.timestamp)}</span>
      </div>
    </div>
  )
}

function DocumentBubble({ msg, apiCall, empresaId, contactPhone }) {
  function handleDownload(e) {
    e.preventDefault()
    // Construye URL con credenciales vía apiCall para archivos protegidos
    const url = `/api/summarizer/${empresaId}/${contactPhone}/docs/${encodeURIComponent(msg.filename)}`
    // Crear link temporal para descarga
    apiCall('GET_BLOB', url, null).then(blob => {
      if (!blob) return
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = msg.filename
      a.click()
      URL.revokeObjectURL(a.href)
    }).catch(() => {
      // Fallback: abrir en nueva pestaña
      window.open(url, '_blank')
    })
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
          <button className="sv-download-btn" onClick={handleDownload}>
            ↓ Descargar
          </button>
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

// ─── SummaryView ──────────────────────────────────────────────────────────────

export default function SummaryView({ empresaId, contactPhone, contactName, apiCall, onBack }) {
  const [messages, setMessages] = useState(null)
  const [error, setError] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const messagesRef = useRef(null)

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

  useEffect(() => { loadMessages() }, [empresaId, contactPhone])

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

  useEffect(() => {
    if (messages && messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [messages])

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

  // Agrupar mensajes por día e insertar separadores
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

  return (
    <div className="sv-container">
      {/* Header */}
      <div className="sv-header">
        <button className="sv-back-btn" onClick={onBack}>← Volver</button>
        <div className="sv-header-info">
          <span className="sv-contact-name">{contactName || contactPhone}</span>
          <span className="sv-contact-phone">{contactPhone}</span>
        </div>
        <button className="sv-md-btn" onClick={handleSync} disabled={syncing} title="Re-sincronizar desde historial">
          {syncing ? '...' : '↻'}
        </button>
        <button className="sv-md-btn" onClick={handleDownloadMd} title="Descargar resumen completo">
          ↓ MD
        </button>
      </div>

      {/* Mensajes */}
      <div className="sv-messages" ref={messagesRef}>
        {!messages && !error && (
          <div className="sv-loading">Cargando...</div>
        )}
        {error && (
          <div className="sv-empty">{error}</div>
        )}
        {messages && messages.length === 0 && (
          <div className="sv-empty">Sin mensajes acumulados</div>
        )}
        {items.map((item, i) => {
          if (item.kind === 'sep') {
            return <DaySeparator key={`sep-${item.day}`} label={item.label} />
          }
          const { msg } = item
          if (msg.type === 'audio') {
            return <AudioBubble key={i} msg={msg} />
          }
          if (msg.type === 'document') {
            return (
              <DocumentBubble
                key={i} msg={msg} apiCall={apiCall}
                empresaId={empresaId} contactPhone={contactPhone}
              />
            )
          }
          return <TextBubble key={i} msg={msg} />
        })}
      </div>
    </div>
  )
}
