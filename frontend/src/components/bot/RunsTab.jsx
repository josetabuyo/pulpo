import { useState, useEffect, useCallback } from 'react'

function statusColor(s) {
  if (s === 'completed') return '#16a34a'
  if (s === 'error')     return '#dc2626'
  if (s === 'running')   return '#2563eb'
  return '#94a3b8'
}

function duration(started, ended) {
  if (!ended) return '—'
  const ms = new Date(ended) - new Date(started)
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function StepRow({ step }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr
        onClick={() => setOpen(o => !o)}
        style={{ cursor: 'pointer', borderBottom: '1px solid #f1f5f9' }}
      >
        <td style={{ padding: '6px 8px', fontWeight: 500 }}>{step.node_type}</td>
        <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 11, color: '#64748b' }}>
          {step.node_id.slice(0, 12)}
        </td>
        <td style={{ padding: '6px 8px', color: statusColor(step.status), fontWeight: 600 }}>
          {step.status}
        </td>
        <td style={{ padding: '6px 8px', color: '#64748b' }}>{step.branch_taken ?? '—'}</td>
        <td style={{ padding: '6px 8px', color: '#94a3b8', fontSize: 12 }}>
          {duration(step.started_at, step.ended_at)}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} style={{ padding: '10px 12px', background: '#f8fafc' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {[['INPUT', step.input_state], ['OUTPUT', step.output_state]].map(([label, data]) => (
                <div key={label}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: '#94a3b8', marginBottom: 4, letterSpacing: 1 }}>
                    {label}
                  </div>
                  <pre style={{
                    fontSize: 11, margin: 0, background: '#fff',
                    border: '1px solid #e2e8f0', borderRadius: 4,
                    padding: '6px 8px', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                    maxHeight: 200, overflow: 'auto',
                  }}>
                    {data ? JSON.stringify(data, null, 2) : 'null'}
                  </pre>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function RunDetail({ run, onClose }) {
  const trigger = run.trigger_data ?? {}
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#94a3b8' }}>
            {run.run_id.slice(0, 8)}…
          </span>
          <span style={{ color: statusColor(run.status), fontWeight: 600, fontSize: 13 }}>
            {run.status}
          </span>
          <span style={{ fontSize: 12, color: '#64748b' }}>
            {duration(run.started_at, run.ended_at)}
          </span>
        </div>
        <button className="btn-ghost btn-sm" onClick={onClose}>← Volver</button>
      </div>

      {trigger.message && (
        <div style={{
          fontSize: 12, color: '#475569', marginBottom: 12,
          background: '#f8fafc', borderRadius: 6, padding: '6px 10px',
          borderLeft: '3px solid #cbd5e1',
        }}>
          <strong>{trigger.canal}</strong> · {trigger.contact_phone} · "{trigger.message}"
        </div>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ background: '#f1f5f9' }}>
            {['Tipo', 'Nodo', 'Status', 'Rama', 'Tiempo'].map(h => (
              <th key={h} style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600, fontSize: 12 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(run.steps ?? []).length === 0
            ? <tr><td colSpan={5} style={{ textAlign: 'center', padding: 24, color: '#94a3b8' }}>Sin steps</td></tr>
            : (run.steps ?? []).map(s => <StepRow key={s.id} step={s} />)
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

  if (selected) return <RunDetail run={selected} onClose={() => setSelected(null)} />

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>
          {runs.length === 0 ? 'Sin ejecuciones' : `${runs.length} ejecuciones recientes`}
        </span>
        <button className="btn-ghost btn-sm" onClick={load}>↺ Actualizar</button>
      </div>

      {runs.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8', fontSize: 13 }}>
          Los flows se loguean automáticamente al disparar.
        </div>
      )}

      {runs.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f1f5f9' }}>
              {['Inicio', 'Flow', 'Status', 'Tiempo', ''].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600, fontSize: 12 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map(run => (
              <tr key={run.run_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '7px 8px', fontSize: 12, color: '#475569' }}>
                  {run.started_at?.slice(5, 16)}
                </td>
                <td style={{ padding: '7px 8px', fontFamily: 'monospace', fontSize: 11, color: '#64748b' }}>
                  {run.flow_id.slice(0, 8)}
                </td>
                <td style={{ padding: '7px 8px' }}>
                  <span style={{ color: statusColor(run.status), fontWeight: 600 }}>{run.status}</span>
                </td>
                <td style={{ padding: '7px 8px', color: '#94a3b8', fontSize: 12 }}>
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
