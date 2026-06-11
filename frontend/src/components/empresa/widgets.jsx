/**
 * Widgets chicos compartidos por las piezas de EmpresaCard.
 */
import { useState } from 'react'

export const STATUS_LABELS = {
  ready: 'Conectado', qr_ready: 'Escaneando', connecting: 'Conectando',
  authenticated: 'Autenticando', disconnected: 'Desconectado',
  failed: 'Error', stopped: 'Sin iniciar', qr_needed: 'Sin iniciar',
}

export function dotColor(status) {
  if (status === 'ready') return '#2196f3'
  if (['connecting'].includes(status)) return '#f59e0b'
  return '#ef4444'
}

export function CopyLinkBtn({ botId }) {
  const [copied, setCopied] = useState(false)

  function getUrl() {
    const base = import.meta.env.VITE_PUBLIC_URL || window.location.origin
    return `${base}/empresa/${botId}`
  }

  function handleClick(e) {
    e.stopPropagation()
    const url = getUrl()
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <span
      title={copied ? '¡Copiado!' : getUrl()}
      onClick={handleClick}
      style={{
        cursor: 'pointer',
        fontSize: 13,
        color: copied ? '#22c55e' : '#475569',
        transition: 'color 0.2s',
        userSelect: 'none',
        lineHeight: 1,
      }}
    >
      {copied ? '✓' : '🔗'}
    </span>
  )
}

export function StatusPill({ status, isTg }) {
  const cls = isTg && status === 'ready' ? 's-tg-ready' : `s-${status ?? 'stopped'}`
  return (
    <span className={`badge ${cls}`}>
      <span className="dot" />
      {STATUS_LABELS[status] || status || 'Sin iniciar'}
    </span>
  )
}
