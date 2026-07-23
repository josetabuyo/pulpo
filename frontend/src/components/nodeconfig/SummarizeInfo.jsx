/**
 * Bloque informativo del nodo summarize: ruta de archivos, consolidados
 * protegidos y link a los resúmenes acumulados.
 */
import { useState, useEffect } from 'react'
import { S } from './styles.js'

function ConsolidationCard({ c }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard.writeText(c.path)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  const consolidatedDate = c.consolidated_at
    ? new Date(c.consolidated_at).toLocaleDateString('es-AR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null
  const limitDate = c.last_message_ts
    ? new Date(c.last_message_ts).toLocaleDateString('es-AR', { day: 'numeric', month: 'short', year: 'numeric' })
    : null
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--tg)', borderRadius: 8,
      padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 15 }}>📦</span>
        <span style={{ fontSize: 12, color: 'var(--tg)', fontWeight: 600, flex: 1 }}>
          {c.name !== c.phone ? c.name : c.phone}
        </span>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
          background: 'var(--success-dim)', color: 'var(--success)', borderRadius: 4,
          padding: '2px 6px',
        }}>🔒 PROTEGIDO</span>
      </div>
      {consolidatedDate && (
        <div style={{ fontSize: 10, color: 'var(--text-subtle)' }}>
          Consolidado el <span style={{ color: 'var(--text-subtle)' }}>{consolidatedDate}</span>
          {limitDate && <> · hasta <span style={{ color: 'var(--text-subtle)' }}>{limitDate}</span></>}
          {c.message_count > 0 && <> · <span style={{ color: 'var(--text-muted)' }}>{c.message_count} msgs</span></>}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <code style={{
          fontSize: 9, color: 'var(--tg)', background: 'var(--bg)',
          padding: '4px 7px', borderRadius: 5, wordBreak: 'break-all',
          flex: 1, lineHeight: 1.5, fontFamily: 'monospace',
        }}>
          {c.path}
        </code>
        <button
          onClick={copy}
          style={{
            fontSize: 9, padding: '3px 7px', borderRadius: 4, cursor: 'pointer', flexShrink: 0,
            background: copied ? 'var(--success-dim)' : 'transparent',
            border: `1px solid ${copied ? 'var(--success)' : 'var(--tg)'}`,
            color: copied ? 'var(--success)' : 'var(--tg)',
            transition: 'all 0.2s',
          }}
        >
          {copied ? '✓' : 'Copiar'}
        </button>
      </div>
    </div>
  )
}

export default function SummarizeInfo({ botId, apiCall, onGoToUIs }) {
  const [absPath, setAbsPath] = useState(null)
  const [consolidations, setConsolidations] = useState([])

  useEffect(() => {
    if (!botId || !apiCall) return
    apiCall('GET', `/summarizer/${botId}`, null)
      .then(data => { if (data?.path) setAbsPath(data.path) })
      .catch(e => console.warn('[SummarizeInfo] path', e))
    apiCall('GET', `/summarizer/${botId}/consolidations`, null)
      .then(data => { if (Array.isArray(data?.consolidations)) setConsolidations(data.consolidations) })
      .catch(e => console.warn('[SummarizeInfo] consolidations', e))
  }, [botId, apiCall])

  const displayPath = absPath || `data/summaries/${botId || '<bot_id>'}/`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Acumula cada mensaje entrante en un archivo <code style={{ color: 'var(--text-subtle)' }}>.md</code> por contacto.
        No produce reply — es un efecto de lado.
      </div>
      <div style={S.fieldWrap}>
        <span style={S.label}>RUTA DE ARCHIVOS</span>
        <code style={{ fontSize: 11, color: 'var(--tg)', background: 'var(--bg)', padding: '5px 8px', borderRadius: 5, wordBreak: 'break-all', userSelect: 'all' }}>
          {displayPath}
        </code>
      </div>

      {consolidations.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={S.label}>CONSOLIDADOS</span>
          {consolidations.map(c => <ConsolidationCard key={c.phone} c={c} />)}
        </div>
      )}

      {botId && onGoToUIs && (
        <button
          onClick={onGoToUIs}
          style={{ fontSize: 12, color: 'var(--brand-light)', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}
        >
          Ver resúmenes acumulados →
        </button>
      )}
    </div>
  )
}
