import { useState, useEffect, useRef, useCallback } from 'react'

// ── Config embebida (espeja monitoring.json) ──────────────────────────────────
const HIGHLIGHT = [
  { pattern: 'ERROR',      color: '#c62828', bg: '#ffebee' },
  { pattern: 'WARNING',    color: '#e65100', bg: '#fff3e0' },
  { pattern: 'Traceback',  color: '#c62828', bg: '#ffebee' },
  { pattern: '200 OK',     color: '#1a7a45', bg: '#e8f5e9' },
  { pattern: 'restored',   color: '#1a7a45', bg: '#e8f5e9' },
  { pattern: 'getUpdates', color: '#1565c0', bg: '#e3f2fd' },
]
const ALERT_PATTERNS = ['Traceback', 'HTTP/1.1 5', 'session lost']

function getLineStyle(line) {
  for (const h of HIGHLIGHT) {
    if (line.includes(h.pattern)) return { color: h.color, background: h.bg }
  }
  return {}
}

// ── Sparkline SVG ─────────────────────────────────────────────────────────────
function Sparkline({ data, color, label }) {
  const W = 180, H = 48
  const max = Math.max(...data, 1)
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * W
      const y = H - (v / max) * (H - 4) - 2
      return `${x},${y}`
    })
    .join(' ')

  return (
    <div className="mon-spark">
      <svg width={W} height={H} style={{ overflow: 'visible' }}>
        <polyline
          points={pts}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {data.map((v, i) => {
          if (v === 0) return null
          const x = (i / (data.length - 1)) * W
          const y = H - (v / max) * (H - 4) - 2
          return <circle key={i} cx={x} cy={y} r="3" fill={color} />
        })}
      </svg>
      <div className="mon-spark-label">
        <span style={{ color }}>{label}</span>
        <span className="mon-spark-cur">{data[data.length - 1]}</span>
      </div>
    </div>
  )
}

// ── Hook de polling ───────────────────────────────────────────────────────────
function useLogPoller(source, pwd, paused) {
  const [lines, setLines] = useState([])
  const [alerts, setAlerts] = useState([])
  const knownLinesRef = useRef(0)

  const fetchLines = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/logs/latest?source=${source}&lines=500`,
        { headers: { 'x-password': pwd } }
      )
      if (!res.ok) return
      const data = await res.json()
      const incoming = data.lines || []
      setLines(incoming)

      // Detectar alertas en líneas nuevas
      const newLines = incoming.slice(knownLinesRef.current)
      knownLinesRef.current = incoming.length
      const found = []
      for (const line of newLines) {
        for (const pat of ALERT_PATTERNS) {
          if (line.includes(pat)) found.push(line.trim())
        }
      }
      if (found.length) setAlerts(prev => [...prev, ...found])
    } catch {}
  }, [source, pwd])

  useEffect(() => {
    knownLinesRef.current = 0
    setLines([])
    fetchLines()
  }, [source])

  useEffect(() => {
    if (paused) return
    const id = setInterval(fetchLines, 2000)
    return () => clearInterval(id)
  }, [fetchLines, paused])

  const clearAlerts = useCallback(() => setAlerts([]), [])
  return { lines, alerts, clearAlerts }
}

// ── Cálculo de sparklines ─────────────────────────────────────────────────────
function buildSparklines(lines) {
  // Últimos 10 minutos, bucket por minuto
  const now = Date.now()
  const reqBuckets = new Array(10).fill(0)
  const errBuckets = new Array(10).fill(0)

  // Timestamp típico: "2024-01-15 14:23:05,123 INFO ..."
  const tsRe = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/

  for (const line of lines) {
    const m = line.match(tsRe)
    if (!m) continue
    const t = new Date(m[1]).getTime()
    const minutesAgo = Math.floor((now - t) / 60000)
    if (minutesAgo < 0 || minutesAgo >= 10) continue
    const idx = 9 - minutesAgo
    reqBuckets[idx]++
    if (line.includes('ERROR') || line.includes('Traceback')) errBuckets[idx]++
  }
  return { reqBuckets, errBuckets }
}

// ── Panel principal ───────────────────────────────────────────────────────────
export default function MonitorPanel({ open, onClose, pwd, onAlertsChange }) {
  const [source, setSource] = useState('backend')
  const [paused, setPaused] = useState(false)
  const [filter, setFilter] = useState('')
  const bottomRef = useRef(null)
  const logRef = useRef(null)
  const userScrolledRef = useRef(false)

  const { lines, alerts, clearAlerts } = useLogPoller(source, pwd, paused)

  useEffect(() => {
    onAlertsChange?.(alerts.length)
  }, [alerts.length])

  const filtered = filter
    ? lines.filter(l => l.toLowerCase().includes(filter.toLowerCase()))
    : lines

  const { reqBuckets, errBuckets } = buildSparklines(lines)

  // Auto-scroll al fondo cuando llegan líneas nuevas, salvo que el usuario haya scrolleado
  useEffect(() => {
    if (!paused && !userScrolledRef.current && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [filtered.length, paused])

  function handleScroll(e) {
    const el = e.currentTarget
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    userScrolledRef.current = !atBottom
  }

  if (!open) return null

  return (
    <div className="mon-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="mon-drawer">

        {/* Header */}
        <div className="mon-header">
          <span className="mon-title">📊 Monitor</span>
          <div className="mon-tabs">
            {['backend', 'frontend'].map(s => (
              <button
                key={s}
                className={`mon-tab${source === s ? ' mon-tab--active' : ''}`}
                onClick={() => { setSource(s); userScrolledRef.current = false }}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="mon-header-actions">
            <button className="btn-ghost btn-sm" onClick={() => setPaused(p => !p)}>
              {paused ? '▶ Reanudar' : '⏸ Pausar'}
            </button>
            <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
          </div>
        </div>

        {/* Alertas */}
        {alerts.length > 0 && (
          <div className="mon-alerts">
            <strong>⚠ {alerts.length} alerta{alerts.length > 1 ? 's' : ''}</strong>
            <button className="btn-ghost btn-sm" onClick={clearAlerts}>Descartar</button>
            <div className="mon-alert-list">
              {alerts.slice(-3).map((a, i) => (
                <div key={i} className="mon-alert-line">{a}</div>
              ))}
            </div>
          </div>
        )}

        {/* Sparklines */}
        <div className="mon-sparks">
          <Sparkline data={reqBuckets} color="#25d366" label="req/min" />
          <Sparkline data={errBuckets} color="#c62828" label="err/min" />
        </div>

        {/* Filtro */}
        <div className="mon-filter-row">
          <input
            className="mon-filter"
            placeholder="Filtrar líneas..."
            value={filter}
            onChange={e => setFilter(e.target.value)}
          />
          <span className="mon-count">{filtered.length} líneas</span>
          {paused && <span className="mon-paused-badge">PAUSADO</span>}
        </div>

        {/* Log */}
        <div className="mon-log" ref={logRef} onScroll={handleScroll}>
          {filtered.length === 0 && (
            <div className="mon-empty">Sin líneas en el log aún...</div>
          )}
          {filtered.map((line, i) => (
            <div key={i} className="mon-line" style={getLineStyle(line)}>
              {line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

      </div>
    </div>
  )
}
