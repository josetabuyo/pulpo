import { useState, useEffect, useCallback } from 'react'
import { humanizeId } from '../../store/flowStore.js'

function statusColor(s) {
  if (s === 'completed') return 'var(--success)'
  if (s === 'error')     return 'var(--danger)'
  if (s === 'running')   return 'var(--tg)'
  return 'var(--text-subtle)'
}

function SimBadge() {
  return (
    <span style={{
      marginLeft: 6, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em',
      color: 'var(--brand-light)', background: 'rgba(167, 139, 250, 0.12)',
      border: '1px solid var(--brand-hover)', borderRadius: 4, padding: '1px 5px',
    }}>
      SIMULADO
    </span>
  )
}

function duration(started, ended) {
  if (!ended) return '—'
  const ms = new Date(ended) - new Date(started)
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function formatDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-AR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ─── Visor JSON colapsable ──────────────────────────────────────────────
function JsonNode({ label, value, depth }) {
  const isObj = value !== null && typeof value === 'object'
  const isEmpty = isObj && Object.keys(value).length === 0
  const [open, setOpen] = useState(depth < 1)

  if (!isObj || isEmpty) {
    return (
      <div style={{ padding: '1px 0 1px 14px' }}>
        {label != null && <span style={{ color: 'var(--tg)' }}>{label}: </span>}
        <span style={{ color: 'var(--text-muted)' }}>
          {isEmpty ? (Array.isArray(value) ? '[]' : '{}') : JSON.stringify(value)}
        </span>
      </div>
    )
  }

  const isArray = Array.isArray(value)
  const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value)

  return (
    <div>
      <div
        onClick={() => setOpen(o => !o)}
        style={{ padding: '1px 0 1px 14px', cursor: 'pointer', userSelect: 'none' }}
      >
        <span style={{ color: 'var(--text-subtle)', display: 'inline-block', width: 12 }}>
          {open ? '▾' : '▸'}
        </span>
        {label != null && <span style={{ color: 'var(--tg)' }}>{label}: </span>}
        <span style={{ color: 'var(--text-subtle)' }}>
          {isArray ? `Array(${entries.length})` : `{${entries.length}}`}
        </span>
      </div>
      {open && (
        <div style={{ borderLeft: '1px solid var(--border)', marginLeft: 5 }}>
          {entries.map(([k, v]) => (
            <JsonNode key={k} label={k} value={v} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function JsonViewer({ data }) {
  if (data == null) return <div style={{ color: 'var(--text-subtle)', fontSize: 12, padding: 8 }}>null</div>
  return (
    <div style={{ fontFamily: 'monospace', fontSize: 12, lineHeight: 1.6 }}>
      <JsonNode label={null} value={data} depth={0} />
    </div>
  )
}

function StepRow({ step, nodeLabels }) {
  const [open, setOpen] = useState(false)
  const label = nodeLabels?.[step.node_id] || step.node_id
  return (
    <>
      <tr
        onClick={() => setOpen(o => !o)}
        style={{ cursor: 'pointer', borderBottom: '1px solid var(--border)' }}
      >
        <td style={{ padding: '6px 8px', fontWeight: 500 }}>{step.node_type}</td>
        <td style={{ padding: '6px 8px', fontSize: 12, color: 'var(--text-muted)' }}>
          {label}
        </td>
        <td style={{ padding: '6px 8px', color: statusColor(step.status), fontWeight: 600 }}>
          {step.status}
        </td>
        <td style={{ padding: '6px 8px', color: 'var(--text-subtle)' }}>{step.branch_taken ?? '—'}</td>
        <td style={{ padding: '6px 8px', color: 'var(--text-subtle)', fontSize: 12 }}>
          {duration(step.started_at, step.ended_at)}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} style={{ padding: '10px 12px', background: 'var(--surface-2)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {[['INPUT', step.input_state], ['OUTPUT', step.output_state]].map(([label, data]) => (
                <div key={label}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-subtle)', marginBottom: 4, letterSpacing: 1 }}>
                    {label}
                  </div>
                  <div style={{
                    background: 'var(--surface)',
                    border: '1px solid var(--border)', borderRadius: 4,
                    padding: '6px 8px',
                    maxHeight: 200, overflow: 'auto',
                  }}>
                    <JsonViewer data={data} />
                  </div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function RunDetail({ run, onClose, botId, apiCall }) {
  const trigger = run.trigger_data ?? {}
  // El mensaje que disparó el run vive en conversation[0] (ver graphs/conversation.py);
  // trigger.message solo existe como fallback en runs viejos o sin conversación.
  const firstMessage = trigger.data?.conversation?.[0]?.content ?? trigger.message
  const [nodeLabels, setNodeLabels] = useState({})

  useEffect(() => {
    let cancelled = false
    apiCall('GET', `/flows/bots/${botId}/${run.flow_id}`, null)
      .then(flow => {
        if (cancelled || !flow?.definition?.nodes) return
        const map = {}
        for (const n of flow.definition.nodes) {
          map[n.id] = n.label || humanizeId(n.id) || n.type
        }
        setNodeLabels(map)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [botId, run.flow_id, apiCall])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-subtle)' }}>
            {run.run_id.slice(0, 8)}…
          </span>
          <span style={{ color: statusColor(run.status), fontWeight: 600, fontSize: 13 }}>
            {run.status}
          </span>
          {run.is_sim && <SimBadge />}
          <span style={{ fontSize: 12, color: 'var(--text-subtle)' }}>
            {duration(run.started_at, run.ended_at)}
          </span>
        </div>
        <button className="btn-ghost btn-sm" onClick={onClose}>← Volver</button>
      </div>

      {firstMessage && (
        <div style={{
          fontSize: 12, color: 'var(--text-muted)', marginBottom: 6,
          background: 'var(--surface-2)', borderRadius: '6px 6px 0 0', padding: '6px 10px',
          borderLeft: '3px solid var(--border-strong)', borderBottom: '1px solid var(--border)',
        }}>
          <strong>{trigger.canal}</strong> · {trigger.contact_phone} · &quot;{firstMessage}&quot;
        </div>
      )}

      <div style={{
        resize: 'vertical', overflow: 'auto', height: 220, minHeight: 90, maxHeight: 600,
        border: '1px solid var(--border)', borderRadius: firstMessage ? '0 0 6px 6px' : 6,
        marginBottom: 14, background: 'var(--surface)', padding: '4px 0',
      }}>
        <JsonViewer data={trigger} />
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ background: 'var(--border)' }}>
            {['Tipo', 'Nodo', 'Status', 'Rama', 'Tiempo'].map(h => (
              <th key={h} style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600, fontSize: 12 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(run.steps ?? []).length === 0
            ? <tr><td colSpan={5} style={{ textAlign: 'center', padding: 24, color: 'var(--text-subtle)' }}>Sin steps</td></tr>
            : (run.steps ?? []).map(s => <StepRow key={s.id} step={s} nodeLabels={nodeLabels} />)
          }
        </tbody>
      </table>
    </div>
  )
}

export default function RunsTab({ botId, apiCall }) {
  const [runs, setRuns]       = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    const data = await apiCall('GET', `/runs/bots/${botId}?limit=30`, null).catch(() => null)
    if (Array.isArray(data)) setRuns(data)
  }, [botId, apiCall])

  useEffect(() => { load() }, [load])

  async function openRun(runId) {
    setLoading(true)
    const data = await apiCall('GET', `/runs/${runId}`, null).catch(() => null)
    setLoading(false)
    if (data?.run_id) setSelected(data)
  }

  if (selected) return <RunDetail run={selected} onClose={() => setSelected(null)} botId={botId} apiCall={apiCall} />

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: 'var(--text-subtle)' }}>
          {runs.length === 0 ? 'Sin ejecuciones' : `${runs.length} ejecuciones recientes`}
        </span>
        <button className="btn-ghost btn-sm" onClick={load}>↺ Actualizar</button>
      </div>

      {runs.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-subtle)', fontSize: 13 }}>
          Los flows se loguean automáticamente al disparar.
        </div>
      )}

      {runs.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--border)' }}>
              {['Inicio', 'Flow', 'Status', 'Tiempo', ''].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600, fontSize: 12 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map(run => (
              <tr key={run.run_id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '7px 8px', fontSize: 12, color: 'var(--text-muted)' }}>
                  {formatDateTime(run.started_at)}
                </td>
                <td style={{ padding: '7px 8px', fontSize: 12, color: 'var(--text-subtle)' }}>
                  {run.flow_name || run.flow_id.slice(0, 8)}
                </td>
                <td style={{ padding: '7px 8px' }}>
                  <span style={{ color: statusColor(run.status), fontWeight: 600 }}>{run.status}</span>
                  {run.is_sim && <SimBadge />}
                </td>
                <td style={{ padding: '7px 8px', color: 'var(--text-subtle)', fontSize: 12 }}>
                  {duration(run.started_at, run.ended_at)}
                </td>
                <td style={{ padding: '7px 8px', textAlign: 'right' }}>
                  <button
                    className="btn-ghost btn-sm"
                    style={{ fontSize: 12, padding: '2px 8px' }}
                    onClick={() => openRun(run.run_id)}
                    disabled={loading}
                  >
                    Ver →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
