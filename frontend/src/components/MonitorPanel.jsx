import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

// ── Highlight lines ────────────────────────────────────────────────────────────
const HIGHLIGHT = [
  { pattern: 'ERROR',     color: '#ef5350', bg: 'rgba(239,83,80,0.13)' },
  { pattern: 'WARNING',   color: '#ff9800', bg: 'rgba(255,152,0,0.11)' },
  { pattern: 'Traceback', color: '#ef5350', bg: 'rgba(239,83,80,0.13)' },
  { pattern: '200 OK',    color: '#66bb6a', bg: 'rgba(102,187,106,0.10)' },
  { pattern: 'restored',  color: '#66bb6a', bg: 'rgba(102,187,106,0.10)' },
  { pattern: ' DEBUG ',   color: '#546e7a', bg: 'rgba(84,110,122,0.08)' },
]

const LEVEL_OPTIONS = [
  { value: 'DEBUG',   label: 'Debug',    color: '#546e7a' },
  { value: 'INFO',    label: 'Info',     color: '#aaa' },
  { value: 'WARNING', label: 'Warnings', color: '#ff9800' },
  { value: 'ERROR',   label: 'Errores',  color: '#ef5350' },
]

function getLineLevel(line) {
  if (line.includes('ERROR') || line.includes('Traceback') || line.includes('[browser:error]')) return 'ERROR'
  if (line.includes('WARNING') || line.includes('⚠')) return 'WARNING'
  if (line.includes(' DEBUG ')) return 'DEBUG'
  return 'INFO'
}
const ALERT_PATTERNS = ['Traceback', 'HTTP/1.1 5', 'session lost']

function getLineStyle(line) {
  for (const h of HIGHLIGHT) {
    if (line.includes(h.pattern)) return { color: h.color, background: h.bg }
  }
  return {}
}

// ── Time windows ───────────────────────────────────────────────────────────────
// bucketMin: tamaño de cada bucket en minutos; buckets: cantidad de puntos en el gráfico
const TIME_WINDOWS = [
  { label: '15m', minutes: 15,  buckets: 15, bucketMin: 1  },
  { label: '30m', minutes: 30,  buckets: 30, bucketMin: 1  },
  { label: '1h',  minutes: 60,  buckets: 30, bucketMin: 2  },
  { label: '3h',  minutes: 180, buckets: 36, bucketMin: 5  },
]

// Cuántas líneas pedir según la ventana de tiempo (150 líneas/min estimado máximo)
function linesForWindow(minutes) {
  return Math.min(5000, minutes * 150)
}

// ── Log parsing ────────────────────────────────────────────────────────────────
const TS_RE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/

function parseTimestamp(line) {
  const m = line.match(TS_RE)
  return m ? new Date(m[1]).getTime() : null
}

function classifyLine(line) {
  if (line.includes('Mensaje de ') || line.includes('[sim] MSG ←')) return 'received'
  if (
    line.includes('Mensaje enviado a') ||
    line.includes('[sim] REPLY →') ||
    line.includes('Respuesta enviada')
  ) return 'replied'
  if (line.includes('ERROR') || line.includes('Traceback') || line.includes('[browser:error]')) return 'error'
  if (line.includes('WARNING') || line.includes('⚠')) return 'warning'
  return 'other'
}

function buildMetrics(lines, windowCfg) {
  const now = Date.now()
  const { buckets, bucketMin, minutes } = windowCfg
  const bucketMs   = bucketMin * 60 * 1000
  const windowStart = now - minutes * 60 * 1000
  const received = new Array(buckets).fill(0)
  const replied  = new Array(buckets).fill(0)
  const errors   = new Array(buckets).fill(0)
  const warnings = new Array(buckets).fill(0)

  for (const line of lines) {
    const t = parseTimestamp(line)
    if (!t || t < windowStart) continue
    const ageMs = now - t
    const idx = buckets - 1 - Math.floor(ageMs / bucketMs)
    if (idx < 0 || idx >= buckets) continue
    const type = classifyLine(line)
    if      (type === 'received') received[idx]++
    else if (type === 'replied')  replied[idx]++
    else if (type === 'error')    errors[idx]++
    else if (type === 'warning')  warnings[idx]++
  }
  return { received, replied, errors, warnings }
}

function buildBucketLabels(windowCfg) {
  const now = Date.now()
  const { buckets, bucketMin, minutes } = windowCfg
  return Array.from({ length: buckets }, (_, i) => {
    const ageMin = minutes - i * bucketMin
    const t  = new Date(now - ageMin * 60 * 1000)
    const hh = t.getHours().toString().padStart(2, '0')
    const mm = t.getMinutes().toString().padStart(2, '0')
    return `${hh}:${mm}`
  })
}

// ── Chart ──────────────────────────────────────────────────────────────────────
const SERIES = [
  { key: 'received', label: 'Mensajes recibidos',   color: '#25d366' },
  { key: 'replied',  label: 'Mensajes respondidos', color: '#42a5f5' },
  { key: 'errors',   label: 'Errores',              color: '#ef5350' },
  { key: 'warnings', label: 'Warnings',             color: '#ff9800' },
]

function MetricChart({ metrics, labels, windowCfg }) {
  const W = 1000, H = 130
  const PAD = { top: 12, right: 16, bottom: 26, left: 36 }
  const iW = W - PAD.left - PAD.right
  const iH = H - PAD.top - PAD.bottom
  const n = labels.length

  const allVals = SERIES.flatMap(s => metrics[s.key] || [])
  const maxVal  = Math.max(...allVals, 1)

  const toX = i  => PAD.left + (n <= 1 ? iW / 2 : (i / (n - 1)) * iW)
  const toY = v  => PAD.top  + iH - (v / maxVal) * iH

  // Labels every ~5-6 points
  const step = n <= 20 ? 2 : n <= 30 ? 4 : 6

  // Y grid lines
  const yTicks = [0, Math.round(maxVal / 2), maxVal]

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      {/* Grid lines + Y labels */}
      {yTicks.map((v, i) => {
        const y = toY(v)
        return (
          <g key={i}>
            <line
              x1={PAD.left} y1={y} x2={W - PAD.right} y2={y}
              stroke="#2e2e2e" strokeWidth="1"
            />
            <text x={PAD.left - 5} y={y + 4} textAnchor="end" fill="#555" fontSize="10">
              {v}
            </text>
          </g>
        )
      })}

      {/* X labels */}
      {labels.map((lbl, i) => {
        if (i % step !== 0 && i !== n - 1) return null
        return (
          <text key={i} x={toX(i)} y={H - 6} textAnchor="middle" fill="#555" fontSize="10">
            {lbl}
          </text>
        )
      })}

      {/* Series lines */}
      {SERIES.map(({ key, color }) => {
        const data = metrics[key] || []
        if (data.every(v => v === 0)) return null
        const pts = data.map((v, i) => `${toX(i)},${toY(v)}`).join(' ')
        return (
          <g key={key}>
            <polyline
              points={pts} fill="none" stroke={color}
              strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"
            />
            {data.map((v, i) =>
              v > 0
                ? <circle key={i} cx={toX(i)} cy={toY(v)} r="3" fill={color} />
                : null
            )}
          </g>
        )
      })}
    </svg>
  )
}

// ── Stat card ──────────────────────────────────────────────────────────────────
function StatCard({ label, value, color }) {
  return (
    <div className="mon-stat">
      <div className="mon-stat-value" style={{ color }}>{value}</div>
      <div className="mon-stat-label">{label}</div>
    </div>
  )
}

// ── Polling hook ───────────────────────────────────────────────────────────────
function useLogPoller(source, pwd, paused, windowMinutes, active) {
  const [lines, setLines] = useState([])
  const [alerts, setAlerts] = useState([])
  const knownRef = useRef(0)

  const fetchLines = useCallback(async () => {
    try {
      const n = linesForWindow(windowMinutes)
      const res = await fetch(
        `/api/logs/latest?source=${source}&lines=${n}`,
        { headers: { 'x-password': pwd } }
      )
      if (!res.ok) return
      const data = await res.json()
      const incoming = data.lines || []
      setLines(incoming)
      const newLines = incoming.slice(knownRef.current)
      knownRef.current = incoming.length
      const found = []
      for (const line of newLines)
        for (const pat of ALERT_PATTERNS)
          if (line.includes(pat)) found.push(line.trim())
      if (found.length) setAlerts(prev => [...prev, ...found])
    } catch {}
  }, [source, pwd, windowMinutes])

  useEffect(() => {
    knownRef.current = 0
    setLines([])
    fetchLines()
  }, [source, windowMinutes])

  // Fetch inmediato al activarse (expandir monitor)
  useEffect(() => {
    if (active) fetchLines()
  }, [active])

  useEffect(() => {
    if (paused || !active) return
    const id = setInterval(fetchLines, 2000)
    return () => clearInterval(id)
  }, [fetchLines, paused, active])

  const clearAlerts = useCallback(() => setAlerts([]), [])
  return { lines, alerts, clearAlerts }
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function MonitorPanel({ pwd, onAlertsChange, active = true }) {
  const [source,       setSource]      = useState('backend')
  const [paused,       setPaused]      = useState(false)
  const [filter,       setFilter]      = useState('')
  const [activeLevels, setActiveLevels] = useState(['INFO', 'WARNING', 'ERROR'])
  const [windowIdx,    setWindowIdx]   = useState(0)

  const bottomRef      = useRef(null)
  const logRef         = useRef(null)
  const userScrolled   = useRef(false)

  const windowCfg = TIME_WINDOWS[windowIdx]
  const { lines, alerts, clearAlerts } = useLogPoller(source, pwd, paused, windowCfg.minutes, active)

  useEffect(() => { onAlertsChange?.(alerts.length) }, [alerts.length])

  const metrics = useMemo(() => buildMetrics(lines, windowCfg), [lines, windowCfg])
  const labels  = useMemo(() => buildBucketLabels(windowCfg),   [windowCfg, lines])

  const totals = useMemo(() => ({
    received: metrics.received.reduce((a, b) => a + b, 0),
    replied:  metrics.replied.reduce((a, b) => a + b, 0),
    errors:   metrics.errors.reduce((a, b) => a + b, 0),
    warnings: metrics.warnings.reduce((a, b) => a + b, 0),
  }), [metrics])

  const filtered = useMemo(() => {
    let r = lines
    if (filter) r = r.filter(l => l.toLowerCase().includes(filter.toLowerCase()))
    r = r.filter(l => activeLevels.includes(getLineLevel(l)))
    return r
  }, [lines, filter, activeLevels])

  useEffect(() => {
    if (!paused && !userScrolled.current && logRef.current)
      logRef.current.scrollTop = logRef.current.scrollHeight
  }, [filtered.length, paused])

  function handleScroll(e) {
    const el = e.currentTarget
    userScrolled.current = el.scrollHeight - el.scrollTop - el.clientHeight > 60
  }

  return (
    <div className="mon-inline">

      {/* Controls bar */}
      <div className="mon-controls">
        <div className="mon-tab-group">
          <span className="mon-tab-label">Fuente</span>
          {['backend', 'frontend'].map(s => (
            <button
              key={s}
              className={`mon-tab${source === s ? ' mon-tab--active' : ''}`}
              onClick={() => { setSource(s); userScrolled.current = false }}
            >{s}</button>
          ))}
        </div>

        <div className="mon-tab-group">
          <span className="mon-tab-label">Ventana</span>
          {TIME_WINDOWS.map((w, i) => (
            <button
              key={w.label}
              className={`mon-tab${windowIdx === i ? ' mon-tab--active' : ''}`}
              onClick={() => setWindowIdx(i)}
            >{w.label}</button>
          ))}
        </div>

        <button
          className="btn-ghost btn-sm mon-pause-btn"
          onClick={() => setPaused(p => !p)}
        >{paused ? '▶ Reanudar' : '⏸ Pausar'}</button>
      </div>

      {/* Stat cards */}
      <div className="mon-stats">
        <StatCard label={`Recibidos — últimos ${windowCfg.label}`}   value={totals.received} color="#25d366" />
        <StatCard label={`Respondidos — últimos ${windowCfg.label}`} value={totals.replied}  color="#42a5f5" />
        <StatCard label={`Errores — últimos ${windowCfg.label}`}     value={totals.errors}   color="#ef5350" />
        <StatCard label={`Warnings — últimos ${windowCfg.label}`}    value={totals.warnings} color="#ff9800" />
      </div>

      {/* Chart */}
      <div className="mon-chart">
        <div className="mon-chart-header">
          <span className="mon-chart-title">
            Actividad por {windowCfg.bucketMin === 1 ? 'minuto' : `${windowCfg.bucketMin} min`} — últimos {windowCfg.label}
          </span>
          <div className="mon-legend">
            {SERIES.map(s => (
              <span key={s.key} className="mon-legend-item">
                <span className="mon-legend-dot" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
        </div>
        <MetricChart metrics={metrics} labels={labels} windowCfg={windowCfg} />
      </div>

      {/* Alerts */}
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

      {/* Log filter row */}
      <div className="mon-filter-row">
        <input
          className="mon-filter"
          placeholder="Filtrar log..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
        <div className="mon-level-checks">
          {LEVEL_OPTIONS.map(({ value, label, color }) => {
            const on = activeLevels.includes(value)
            return (
              <label
                key={value}
                className="mon-level-check"
                style={{ color: on ? color : '#444' }}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => setActiveLevels(prev =>
                    prev.includes(value) ? prev.filter(l => l !== value) : [...prev, value]
                  )}
                />
                {label}
              </label>
            )
          })}
        </div>
        <span className="mon-count">{filtered.length} líneas</span>
        {paused && <span className="mon-paused-badge">PAUSADO</span>}
      </div>

      {/* Log */}
      <div className="mon-log" ref={logRef} onScroll={handleScroll}>
        {filtered.length === 0 && (
          <div className="mon-empty">Sin líneas en el log aún...</div>
        )}
        {filtered.map((line, i) => (
          <div key={i} className="mon-line" style={getLineStyle(line)}>{line}</div>
        ))}
        <div ref={bottomRef} />
      </div>

    </div>
  )
}
