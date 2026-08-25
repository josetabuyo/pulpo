import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

// TS port note: reescrito completo (2026-07-22) -- antes pegaba a
// /api/logs/latest (tail de archivo de texto del proceso Python local), que
// no existe en web/ (Vercel serverless no tiene filesystem persistente ni
// proceso long-lived para eso). Los logs de infraestructura (crashes HTTP,
// 500s) ya tienen su propio lugar nativo con niveles y volumen en el tiempo:
// el dashboard de Vercel (Runtime Logs) / `vercel logs --level error`. Este
// panel se enfoca en actividad de NEGOCIO -- triggers de flow, éxitos,
// errores -- que Vercel no puede ver, alimentado por /api/runs/stats
// (flow_runs en Neon). Ver management/HANDOFF_VERCEL_DEEP_MIGRATION.md.

// Paleta de status (dataviz skill) -- revalidada contra la superficie Dark
// Ocean de este panel (var(--surface) #111c30, migración Dark Ocean 2026-07-23):
// node scripts/validate_palette.js "#0ca30c,#d03b3b" --mode dark --surface "#111c30"
// -> PASS (ΔE 12.4, piso de la banda CVD -- por eso el gráfico también lleva
// leyenda + etiquetas directas + línea sólida encima del fill, no depende solo
// del color). Los mismos valores servían contra la superficie negra anterior
// (#141414); no hizo falta subir luminosidad.
const STATUS = {
  success: { label: 'Éxitos',    color: '#0ca30c' },
  error:   { label: 'Errores',   color: '#d03b3b' },
  pending: { label: 'En curso',  color: '#5e6e8f' }, // = --text-subtle (hex literal: fill SVG no resuelve var() de forma confiable en todos los browsers)
}

// Cada ventana define su propio intervalo de refresco: cuanto más chica la
// ventana, más frecuente hay que refrescar para que un trigger nuevo se vea
// enseguida (15m con un poll de 8s tarda casi la mitad de la ventana en
// aparecer); ventanas grandes no necesitan poll rápido -- el bucket ya es de
// horas/días, así que refrescar cada pocos segundos solo generaba requests
// de más sin cambiar lo que se ve en pantalla.
const TIME_WINDOWS = [
  { label: '15m', since: '15m', pollMs: 3000  },
  { label: '1h',  since: '1h',  pollMs: 5000  },
  { label: '6h',  since: '6h',  pollMs: 15000 },
  { label: '24h', since: '24h', pollMs: 30000 },
  { label: '7d',  since: '7d',  pollMs: 60000 },
]

function formatBucketLabel(iso, bucketMinutes) {
  const d = new Date(iso)
  if (bucketMinutes >= 60 * 24) {
    return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' })
  }
  if (bucketMinutes >= 60) {
    return d.toLocaleString('es-AR', { day: '2-digit', hour: '2-digit' }).replace(',', '')
  }
  return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
}

// ── Polling hook ───────────────────────────────────────────────────────────
function useRunStats(since, active, botId, pollMs) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const fetchStats = useCallback(async () => {
    try {
      const qs = new URLSearchParams({ since })
      if (botId) qs.set('botId', botId)
      const res = await fetch(`/api/runs/stats?${qs}`, { credentials: 'include' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setError(null)
    } catch (e) {
      setError(e.message || 'fetch falló')
    }
  }, [since, botId])

  useEffect(() => { setData(null); fetchStats() }, [since, fetchStats])

  useEffect(() => {
    if (!active) return
    const id = setInterval(fetchStats, pollMs)
    return () => clearInterval(id)
  }, [fetchStats, active, pollMs])

  return { data, error, refetch: fetchStats }
}

// ── Chart: áreas solapadas éxito/error, un solo eje ─────────────────────────
// Selección por drag (mousedown+move+up), ADEMÁS del hover que ya existía --
// al soltar, emite el rango de timestamps bajo la selección vía
// `onRangeSelect(fromIso, toIso)`. Consumido por BotCard.jsx para saltar a
// la tab "Ejecuciones" con ese rango como filtro (ver RunsTab.jsx).
function OverlapChart({ buckets, bucketMinutes, onRangeSelect, selectedRange }) {
  const [hoverIdx, setHoverIdx] = useState(null)
  const [dragStartIdx, setDragStartIdx] = useState(null)
  const [dragIdx, setDragIdx] = useState(null)
  const svgRef = useRef(null)

  const W = 1000, H = 220
  const PAD = { top: 16, right: 16, bottom: 28, left: 40 }
  const iW = W - PAD.left - PAD.right
  const iH = H - PAD.top - PAD.bottom
  const n = buckets.length

  // Banda de referencia del rango actualmente filtrado (recalculada desde
  // timestamps absolutos en cada render -- los buckets se re-anclan a
  // `now - ventana` en cada poll, así que cachear índices los desincroniza).
  const bucketMs = bucketMinutes * 60 * 1000
  const firstBucketMs = n > 0 ? new Date(buckets[0].startedAt).getTime() : null
  let selRange = null
  if (selectedRange?.from != null && selectedRange?.to != null && firstBucketMs != null) {
    const loIdxRaw = (selectedRange.from - firstBucketMs) / bucketMs
    const hiIdxRaw = (selectedRange.to - firstBucketMs) / bucketMs
    const loIdx = Math.floor(loIdxRaw)
    const hiIdx = Math.ceil(hiIdxRaw) - 1
    if (hiIdx >= 0 && loIdx < n) {
      selRange = { lo: Math.max(0, loIdx), hi: Math.min(n - 1, hiIdx) }
    }
  }

  const maxVal = Math.max(1, ...buckets.flatMap(b => [b.success, b.error]))
  const toX = i => PAD.left + (n <= 1 ? iW / 2 : (i / (n - 1)) * iW)
  const toY = v => PAD.top + iH - (v / maxVal) * iH

  const areaPath = (key) => {
    const top = buckets.map((b, i) => `${toX(i)},${toY(b[key])}`).join(' L')
    return `M${PAD.left},${toY(0)} L${top} L${toX(n - 1)},${toY(0)} Z`
  }
  const linePath = (key) =>
    buckets.map((b, i) => `${toX(i)},${toY(b[key])}`).join(' L')

  const yTicks = [0, Math.round(maxVal / 2), maxVal]
  const xStep = n <= 12 ? 1 : n <= 30 ? Math.ceil(n / 12) : Math.ceil(n / 8)

  function idxAt(e) {
    const rect = svgRef.current.getBoundingClientRect()
    const relX = ((e.clientX - rect.left) / rect.width) * W
    const idx = Math.round(((relX - PAD.left) / iW) * (n - 1))
    return idx >= 0 && idx < n ? idx : null
  }

  function handleMove(e) {
    const idx = idxAt(e)
    setHoverIdx(idx)
    if (dragStartIdx != null) setDragIdx(idx)
  }

  function handleDown(e) {
    const idx = idxAt(e)
    if (idx == null) return
    setDragStartIdx(idx)
    setDragIdx(idx)
  }

  function handleUp() {
    if (dragStartIdx == null || dragIdx == null || !onRangeSelect) {
      setDragStartIdx(null)
      setDragIdx(null)
      return
    }
    const lo = Math.min(dragStartIdx, dragIdx)
    const hi = Math.max(dragStartIdx, dragIdx)
    if (hi > lo) {
      const fromIso = buckets[lo].startedAt
      const toIso = new Date(new Date(buckets[hi].startedAt).getTime() + bucketMinutes * 60 * 1000).toISOString()
      onRangeSelect(fromIso, toIso)
    }
    setDragStartIdx(null)
    setDragIdx(null)
  }

  const hover = hoverIdx != null ? buckets[hoverIdx] : null
  const selecting = dragStartIdx != null && dragIdx != null && dragIdx !== dragStartIdx
  const selLo = selecting ? Math.min(dragStartIdx, dragIdx) : null
  const selHi = selecting ? Math.max(dragStartIdx, dragIdx) : null

  return (
    <div style={{ position: 'relative' }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', height: 'auto', display: 'block', cursor: 'crosshair', userSelect: 'none' }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIdx(null)}
        onMouseDown={handleDown}
        onMouseUp={handleUp}
      >
        {yTicks.map((v, i) => {
          const y = toY(v)
          return (
            <g key={i}>
              <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} stroke="#24314b" strokeWidth="1" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end" fill="#5e6e8f" fontSize="10">{v}</text>
            </g>
          )
        })}

        {buckets.map((b, i) => (i % xStep === 0 || i === n - 1) ? (
          <text key={i} x={toX(i)} y={H - 8} textAnchor="middle" fill="#5e6e8f" fontSize="10">
            {formatBucketLabel(b.startedAt, bucketMinutes)}
          </text>
        ) : null)}

        {selRange && (
          <g>
            <rect
              x={toX(selRange.lo)} y={PAD.top} width={Math.max(1, toX(selRange.hi) - toX(selRange.lo))} height={iH}
              fill="#7c8dc9" fillOpacity="0.10"
            />
            <line x1={toX(selRange.lo)} y1={PAD.top} x2={toX(selRange.lo)} y2={H - PAD.bottom} stroke="#7c8dc9" strokeWidth="1.5" strokeDasharray="4,3" />
            <line x1={toX(selRange.hi)} y1={PAD.top} x2={toX(selRange.hi)} y2={H - PAD.bottom} stroke="#7c8dc9" strokeWidth="1.5" strokeDasharray="4,3" />
            <text x={toX(selRange.lo)} y={PAD.top - 4} fill="#7c8dc9" fontSize="10">Filtro</text>
          </g>
        )}

        {/* Éxitos: fill translúcido + línea sólida encima (secondary encoding, no depende solo del color) */}
        <path d={areaPath('success')} fill={STATUS.success.color} fillOpacity="0.22" />
        <path d={linePath('success')} fill="none" stroke={STATUS.success.color} strokeWidth="2" strokeLinejoin="round" />

        {/* Errores: mismo tratamiento, dibujado encima para que el solapamiento sea legible en ambas direcciones */}
        <path d={areaPath('error')} fill={STATUS.error.color} fillOpacity="0.30" />
        <path d={linePath('error')} fill="none" stroke={STATUS.error.color} strokeWidth="2" strokeLinejoin="round" />

        {hover && !selecting && (
          <g>
            <line x1={toX(hoverIdx)} y1={PAD.top} x2={toX(hoverIdx)} y2={H - PAD.bottom} stroke="#33436a" strokeWidth="1" strokeDasharray="3,3" />
            <circle cx={toX(hoverIdx)} cy={toY(hover.success)} r="4" fill={STATUS.success.color} stroke="#111c30" strokeWidth="2" />
            <circle cx={toX(hoverIdx)} cy={toY(hover.error)} r="4" fill={STATUS.error.color} stroke="#111c30" strokeWidth="2" />
          </g>
        )}

        {selecting && (
          <rect
            x={toX(selLo)} y={PAD.top} width={toX(selHi) - toX(selLo)} height={iH}
            fill="#7c8dc9" fillOpacity="0.18" stroke="#7c8dc9" strokeWidth="1"
          />
        )}
      </svg>

      {hover && (
        <div
          className="mon-tooltip"
          style={{ left: `${(toX(hoverIdx) / W) * 100}%` }}
        >
          <div className="mon-tooltip-time">{formatBucketLabel(hover.startedAt, bucketMinutes)}</div>
          <div><span style={{ color: STATUS.success.color }}>●</span> {STATUS.success.label}: {hover.success}</div>
          <div><span style={{ color: STATUS.error.color }}>●</span> {STATUS.error.label}: {hover.error}</div>
          <div><span style={{ color: STATUS.pending.color }}>●</span> {STATUS.pending.label}: {hover.pending}</div>
        </div>
      )}
    </div>
  )
}

// ── Stat card ─────────────────────────────────────────────────────────────
function StatCard({ label, value, color }) {
  return (
    <div className="mon-stat">
      <div className="mon-stat-value" style={{ color }}>{value}</div>
      <div className="mon-stat-label">{label}</div>
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────
export default function MonitorPanel({
  active = true, botId, onRangeSelect, selectedRange, onClearRange, onRefresh,
  windowLabel, onWindowChange, // controlado opcional -- si no vienen, usa estado interno (uso standalone en el Monitor global)
}) {
  const [internalWindowIdx, setInternalWindowIdx] = useState(1) // default 1h
  const [paused, setPaused] = useState(false)
  const [zoomed, setZoomed] = useState(false)
  const windowIdx = windowLabel != null
    ? Math.max(0, TIME_WINDOWS.findIndex(w => w.label === windowLabel))
    : internalWindowIdx
  const win = TIME_WINDOWS[windowIdx] || TIME_WINDOWS[1]

  function selectWindow(i) {
    if (onWindowChange) onWindowChange(TIME_WINDOWS[i].label)
    else setInternalWindowIdx(i)
  }

  const { data, error, refetch } = useRunStats(win.since, active && !paused, botId, win.pollMs)

  const allBuckets = data?.buckets ?? []
  const bucketMinutes = data?.bucketMinutes ?? 1

  const bucketMs = bucketMinutes * 60 * 1000
  const firstBucketMs = allBuckets.length > 0 ? new Date(allBuckets[0].startedAt).getTime() : null
  let visibleRangeIdx = null
  if (selectedRange?.from != null && selectedRange?.to != null && firstBucketMs != null) {
    const loIdx = Math.max(0, Math.floor((selectedRange.from - firstBucketMs) / bucketMs))
    const hiIdx = Math.min(allBuckets.length - 1, Math.ceil((selectedRange.to - firstBucketMs) / bucketMs) - 1)
    if (hiIdx >= loIdx) visibleRangeIdx = { lo: loIdx, hi: hiIdx }
  }
  const hasActiveRange = selectedRange?.from != null || selectedRange?.to != null
  const rangeOutOfWindow = hasActiveRange && !visibleRangeIdx

  const buckets = (zoomed && visibleRangeIdx)
    ? allBuckets.slice(visibleRangeIdx.lo, visibleRangeIdx.hi + 1)
    : allBuckets

  const rangeVisible = visibleRangeIdx != null
  useEffect(() => {
    if (!rangeVisible) setZoomed(false)
  }, [rangeVisible])

  function handleRefresh() {
    refetch()
    onRefresh?.()
  }

  function formatRangeChip() {
    if (!selectedRange?.from) return null
    const fmt = t => new Date(t).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    return `${fmt(selectedRange.from)} → ${selectedRange.to ? fmt(selectedRange.to) : '…'}`
  }

  const totals = useMemo(() => buckets.reduce((acc, b) => ({
    success: acc.success + b.success,
    error: acc.error + b.error,
    pending: acc.pending + b.pending,
  }), { success: 0, error: 0, pending: 0 }), [buckets])

  const total = totals.success + totals.error
  const errorRate = total > 0 ? ((totals.error / total) * 100).toFixed(1) : '0.0'

  return (
    <div className="mon-inline">
      <div className="mon-controls">
        <div className="mon-tab-group">
          <span className="mon-tab-label">Ventana</span>
          {TIME_WINDOWS.map((w, i) => (
            <button
              key={w.label}
              className={`mon-tab${windowIdx === i ? ' mon-tab--active' : ''}`}
              onClick={() => selectWindow(i)}
            >{w.label}</button>
          ))}
        </div>
        <div className="mon-actions">
          <button className="btn-ghost btn-sm" onClick={handleRefresh}>↺ Actualizar</button>
          <button className="btn-ghost btn-sm" onClick={() => setPaused(p => !p)}>
            {paused ? '▶ Reanudar' : '⏸ Pausar'}
          </button>
        </div>
      </div>

      {hasActiveRange && (
        <div className="mon-range-chip">
          <span>Filtrado: {formatRangeChip()}</span>
          {visibleRangeIdx && (
            <button className="btn-ghost btn-sm" onClick={() => setZoomed(z => !z)}>
              {zoomed ? '🔍 Ver ventana completa' : '🔍 Zoom al filtro'}
            </button>
          )}
          {rangeOutOfWindow && <span className="mon-range-chip__warn">fuera de la ventana visible</span>}
          <button className="btn-ghost btn-sm" onClick={onClearRange}>✕ Quitar filtro</button>
        </div>
      )}

      <div className="mon-stats">
        <StatCard label={`Éxitos — últimos ${win.label}`}  value={totals.success} color={STATUS.success.color} />
        <StatCard label={`Errores — últimos ${win.label}`} value={totals.error}   color={STATUS.error.color} />
        <StatCard label={`En curso — últimos ${win.label}`} value={totals.pending} color={STATUS.pending.color} />
        <StatCard label="Tasa de error" value={`${errorRate}%`} color={totals.error > 0 ? STATUS.error.color : '#9aaac8'} />
      </div>

      <div className="mon-chart">
        <div className="mon-chart-header">
          <span className="mon-chart-title">
            Triggers de flow por {bucketMinutes >= 60 * 24 ? `${bucketMinutes / (60 * 24)}d` : bucketMinutes >= 60 ? `${bucketMinutes / 60}h` : `${bucketMinutes}min`} — últimos {win.label}
          </span>
          <div className="mon-legend">
            <span className="mon-legend-item"><span className="mon-legend-dot" style={{ background: STATUS.success.color }} />{STATUS.success.label}</span>
            <span className="mon-legend-item"><span className="mon-legend-dot" style={{ background: STATUS.error.color }} />{STATUS.error.label}</span>
            <span className="mon-legend-item"><span className="mon-legend-dot" style={{ background: STATUS.pending.color }} />{STATUS.pending.label}</span>
          </div>
        </div>

        {error && <div className="mon-empty">Error consultando métricas: {error}</div>}
        {!error && !data && <div className="mon-empty">Cargando…</div>}
        {!error && data && buckets.length > 0 && (
          <>
            <OverlapChart buckets={buckets} bucketMinutes={bucketMinutes} onRangeSelect={onRangeSelect} selectedRange={selectedRange} />
            {onRangeSelect && (
              <div style={{ fontSize: 11, color: '#5e6e8f', marginTop: 4 }}>
                Arrastrá sobre el gráfico para filtrar Ejecuciones por ese rango.
              </div>
            )}
          </>
        )}
        {!error && data && buckets.length === 0 && (
          <div className="mon-empty">Sin actividad de flows en esta ventana.</div>
        )}
      </div>
    </div>
  )
}
