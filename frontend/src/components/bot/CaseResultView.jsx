/**
 * Vista "Ver" de una corrida puntual: conversación en forma de chat +
 * validaciones + la imagen del flow con la rama resaltada que compone el
 * reporte de la corrida (capturada server-side sin importar si la disparó
 * la UI o el CLI, ver web/lib/business/flow-capture.ts), más el mismo
 * gemelo interactivo en vivo (FlowExecutionTwin.jsx) para explorar. Todo en
 * un único panel scrolleable, accesible tanto desde el ícono "Ver" de la
 * fila de un caso (última corrida) como desde cada corrida en la vista
 * "Resultados".
 */
import FlowExecutionTwin from './FlowExecutionTwin.jsx'

function StatusBadge({ status }) {
  const label = status === 'passed' ? 'OK' : status === 'error' ? 'ERROR' : 'REVISAR'
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 10,
      background: status === 'passed' ? 'var(--success-dim)' : 'var(--danger-dim, #fee2e2)',
      color: status === 'passed' ? 'var(--success)' : 'var(--danger)',
    }}>
      {label}
    </span>
  )
}

function ChatTurn({ turn }) {
  return (
    <div style={{
      fontSize: 13, marginBottom: 6, padding: '7px 10px', borderRadius: 8,
      background: turn.role === 'user' ? 'var(--surface-2)' : 'var(--surface)',
      marginLeft: turn.role === 'bot' ? 20 : 0, marginRight: turn.role === 'user' ? 20 : 0,
      maxWidth: '85%',
    }}>
      <strong style={{ fontSize: 10, color: 'var(--text-subtle)', display: 'block', marginBottom: 2 }}>
        {turn.role === 'user' ? 'Vecino' : 'Bot'}
      </strong>
      <div>{turn.text || '(sin respuesta)'}</div>
    </div>
  )
}

// data: URLs no siempre abren en pestaña nueva (Chrome bloquea navegación de
// top-frame a data: en algunos contextos, target="_blank" incluido) --
// convertir a blob: URL es lo que anda siempre.
function openImageFullSize(dataUrl) {
  const [meta, base64] = dataUrl.split(',')
  const mime = meta.match(/data:(.*);base64/)?.[1] || 'image/png'
  const bytes = atob(base64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const blob = new Blob([arr], { type: mime })
  window.open(URL.createObjectURL(blob), '_blank')
}

function CheckResultRow({ check }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12, padding: '4px 0' }}>
      <span style={{ color: check.passed ? 'var(--success)' : 'var(--danger)' }}>
        {check.kind === 'log' ? '·' : check.passed ? '✓' : '✗'}
      </span>
      <div>
        <span style={{ color: 'var(--text)' }}>{check.label}</span>
        {check.detail && <div style={{ color: 'var(--text-subtle)', fontFamily: 'monospace', fontSize: 11 }}>{check.detail}</div>}
      </div>
    </div>
  )
}

export default function CaseResultView({ run, apiCall, onClose }) {
  if (!run) return null
  const failed = (run.check_results || []).filter(c => c.kind === 'assert' && !c.passed).length

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: 1200, width: '95vw', maxHeight: '92vh', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4, gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <StatusBadge status={run.status} />
            <strong style={{ fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {run.test_case_title}
            </strong>
          </div>
          <button className="btn-ghost btn-sm" onClick={onClose} title="Cerrar">✕</button>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-subtle)', marginBottom: 16 }}>
          {run.started_at ? new Date(run.started_at).toLocaleString('es-AR') : ''}
          {run.status !== 'passed' && !run.error_message ? ` · ${failed} validación${failed !== 1 ? 'es' : ''} sin pasar` : ''}
        </div>

        {run.error_message && (
          <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 16 }}>{run.error_message}</div>
        )}

        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8 }}>CONVERSACIÓN</div>
        <div style={{ marginBottom: 20 }}>
          {(run.turns || []).map((t, i) => <ChatTurn key={i} turn={t} />)}
        </div>

        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8 }}>VALIDACIONES</div>
        <div style={{ marginBottom: 20 }}>
          {(run.check_results || []).length
            ? run.check_results.map((c, i) => <CheckResultRow key={i} check={c} />)
            : <div style={{ fontSize: 12, color: 'var(--text-subtle)' }}>Sin validaciones configuradas para este caso.</div>}
        </div>

        {run.diagram_image && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)' }}>
                IMAGEN DEL REPORTE (camino recorrido en esta corrida)
              </span>
              <div style={{ display: 'flex', gap: 12 }}>
                <button
                  type="button"
                  onClick={() => openImageFullSize(run.diagram_image)}
                  style={{ fontSize: 11, color: 'var(--brand)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
                >
                  🔍 Ver tamaño completo
                </button>
                <a href={run.diagram_image} download={`test-run-${run.id}.png`} style={{ fontSize: 11, color: 'var(--brand)' }}>
                  ⭳ Descargar
                </a>
              </div>
            </div>
            <div
              onClick={() => openImageFullSize(run.diagram_image)}
              title="Clic para ver a tamaño completo"
              style={{
                display: 'block', flexShrink: 0, marginBottom: 20, border: '1px solid var(--surface-2)', borderRadius: 8,
                overflow: 'auto', background: 'var(--bg)', height: 480, cursor: 'zoom-in',
              }}
            >
              <img src={run.diagram_image} alt={`Flow de "${run.test_case_title}" con el camino recorrido resaltado`} style={{ width: '100%', display: 'block' }} />
            </div>
          </>
        )}

        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8 }}>
          FLOW EN VIVO (solo lectura — mismo resaltado, explorable con zoom/pan)
        </div>
        <FlowExecutionTwin flowSnapshot={run.flow_snapshot} steps={run.steps} apiCall={apiCall} />
      </div>
    </div>
  )
}
