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
      background: '#0a1628', border: '1px solid #1e3a5f', borderRadius: 8,
      padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 15 }}>📦</span>
        <span style={{ fontSize: 12, color: '#93c5fd', fontWeight: 600, flex: 1 }}>
          {c.name !== c.phone ? c.name : c.phone}
        </span>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
          background: '#14532d', color: '#4ade80', borderRadius: 4,
          padding: '2px 6px',
        }}>🔒 PROTEGIDO</span>
      </div>
      {consolidatedDate && (
        <div style={{ fontSize: 10, color: '#475569' }}>
          Consolidado el <span style={{ color: '#94a3b8' }}>{consolidatedDate}</span>
          {limitDate && <> · hasta <span style={{ color: '#94a3b8' }}>{limitDate}</span></>}
          {c.message_count > 0 && <> · <span style={{ color: '#64748b' }}>{c.message_count} msgs</span></>}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <code style={{
          fontSize: 9, color: '#7dd3fc', background: '#0f172a',
          padding: '4px 7px', borderRadius: 5, wordBreak: 'break-all',
          flex: 1, lineHeight: 1.5, fontFamily: 'monospace',
        }}>
          {c.path}
        </code>
        <button
          onClick={copy}
          style={{
            fontSize: 9, padding: '3px 7px', borderRadius: 4, cursor: 'pointer', flexShrink: 0,
            background: copied ? '#166534' : 'transparent',
            border: `1px solid ${copied ? '#16a34a' : '#1e3a5f'}`,
            color: copied ? '#4ade80' : '#3b82f6',
            transition: 'all 0.2s',
          }}
        >
          {copied ? '✓' : 'Copiar'}
        </button>
      </div>
    </div>
  )
}

export default function SummarizeInfo({ empresaId, apiCall, onGoToUIs }) {
  const [absPath, setAbsPath] = useState(null)
  const [consolidations, setConsolidations] = useState([])

  useEffect(() => {
    if (!empresaId || !apiCall) return
    apiCall('GET', `/summarizer/${empresaId}`, null)
      .then(data => { if (data?.path) setAbsPath(data.path) })
      .catch(e => console.warn('[SummarizeInfo] path', e))
    apiCall('GET', `/summarizer/${empresaId}/consolidations`, null)
      .then(data => { if (Array.isArray(data?.consolidations)) setConsolidations(data.consolidations) })
      .catch(e => console.warn('[SummarizeInfo] consolidations', e))
  }, [empresaId, apiCall])

  const displayPath = absPath || `data/summaries/${empresaId || '<empresa_id>'}/`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5 }}>
        Acumula cada mensaje entrante en un archivo <code style={{ color: '#94a3b8' }}>.md</code> por contacto.
        No produce reply — es un efecto de lado.
      </div>
      <div style={S.fieldWrap}>
        <span style={S.label}>RUTA DE ARCHIVOS</span>
        <code style={{ fontSize: 11, color: '#7dd3fc', background: '#0f172a', padding: '5px 8px', borderRadius: 5, wordBreak: 'break-all', userSelect: 'all' }}>
          {displayPath}
        </code>
      </div>

      {consolidations.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={S.label}>CONSOLIDADOS</span>
          {consolidations.map(c => <ConsolidationCard key={c.phone} c={c} />)}
        </div>
      )}

      {empresaId && onGoToUIs && (
        <button
          onClick={onGoToUIs}
          style={{ fontSize: 12, color: '#818cf8', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}
        >
          Ver resúmenes acumulados →
        </button>
      )}
    </div>
  )
}
