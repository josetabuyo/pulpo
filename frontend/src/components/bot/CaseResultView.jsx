/**
 * Vista "Ver" de una corrida puntual: layout partido en 2 -- a la izquierda
 * la conversación completa en forma de chat, a la derecha arriba el gemelo
 * interactivo del flow en solo lectura (FlowExecutionTwin.jsx, mismo
 * resaltado del camino recorrido) y abajo el mosaico de validaciones que se
 * corrieron. Accesible tanto desde el ícono "Ver" de la fila de un caso
 * (última corrida) como desde cada corrida en la vista "Resultados", con
 * flechas ▲/▼ para navegar entre casos sin cerrar el reporte (la lista y el
 * índice viven en TestCasesTab.jsx, acá solo se consumen via onNavigate).
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

function NavButton({ dir, disabled, onClick }) {
  return (
    <button
      className="btn-ghost btn-sm"
      title={dir === 'prev' ? 'Caso anterior' : 'Caso siguiente'}
      disabled={disabled}
      onClick={onClick}
      style={{ lineHeight: 1 }}
    >
      {dir === 'prev' ? '▲' : '▼'}
    </button>
  )
}

export default function CaseResultView({ run, apiCall, onClose, onNavigate, canPrev, canNext, navigating }) {
  if (!run) return null
  const failed = (run.check_results || []).filter(c => c.kind === 'assert' && !c.passed).length

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: 1400, width: '95vw', height: '92vh', display: 'flex', flexDirection: 'column' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4, gap: 10, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <StatusBadge status={run.status} />
            <strong style={{ fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {run.test_case_title}
            </strong>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {onNavigate && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginRight: 4 }}>
                <NavButton dir="prev" disabled={!canPrev || navigating} onClick={() => onNavigate('prev')} />
                <NavButton dir="next" disabled={!canNext || navigating} onClick={() => onNavigate('next')} />
              </div>
            )}
            <button className="btn-ghost btn-sm" onClick={onClose} title="Cerrar">✕</button>
          </div>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-subtle)', marginBottom: 12, flexShrink: 0 }}>
          {run.started_at ? new Date(run.started_at).toLocaleString('es-AR') : ''}
          {run.status !== 'passed' && !run.error_message ? ` · ${failed} validación${failed !== 1 ? 'es' : ''} sin pasar` : ''}
          {run.diagram_image && (
            <>
              {' · '}
              <button
                type="button"
                onClick={() => openImageFullSize(run.diagram_image)}
                style={{ fontSize: 11, color: 'var(--brand)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
              >
                🔍 Imagen del reporte
              </button>
              {' '}
              <a href={run.diagram_image} download={`test-run-${run.id}.png`} style={{ fontSize: 11, color: 'var(--brand)' }}>
                ⭳ Descargar
              </a>
            </>
          )}
        </div>

        {run.error_message && (
          <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 12, flexShrink: 0 }}>{run.error_message}</div>
        )}

        <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0, opacity: navigating ? 0.5 : 1 }}>
          <div style={{ flex: '1 1 40%', minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8, flexShrink: 0 }}>CONVERSACIÓN</div>
            <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
              {(run.turns || []).map((t, i) => <ChatTurn key={i} turn={t} />)}
            </div>
          </div>

          <div style={{ flex: '1 1 60%', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
            <div style={{ flex: '1 1 55%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8, flexShrink: 0 }}>
                FLOW (solo lectura — camino recorrido resaltado, explorable con zoom/pan)
              </div>
              <div style={{ flex: 1, minHeight: 0, border: '1px solid var(--surface-2)', borderRadius: 8, overflow: 'hidden' }}>
                <FlowExecutionTwin flowSnapshot={run.flow_snapshot} steps={run.steps} apiCall={apiCall} />
              </div>
            </div>

            <div style={{ flex: '1 1 45%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8, flexShrink: 0 }}>VALIDACIONES</div>
              <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, border: '1px solid var(--surface-2)', borderRadius: 8, padding: '8px 12px' }}>
                {(run.check_results || []).length
                  ? run.check_results.map((c, i) => <CheckResultRow key={i} check={c} />)
                  : <div style={{ fontSize: 12, color: 'var(--text-subtle)' }}>Sin validaciones configuradas para este caso.</div>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
