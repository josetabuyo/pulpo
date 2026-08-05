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
import { useState } from 'react'
import FlowExecutionTwin from './FlowExecutionTwin.jsx'

// Badge de estado de una corrida -- usado tanto acá (header del detalle)
// como en la fila de la lista de "Casos" y en RunDetail (TestCasesTab.jsx),
// para que el mismo caso se lea igual en los tres lugares.
export function StatusBadge({ status, failedChecks }) {
  const label = status === 'passed' ? 'OK'
    : status === 'error' ? 'ERROR'
    : failedChecks ? `REVISAR (${failedChecks})` : 'REVISAR'
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

// Badge para un caso que todavía no tiene ninguna corrida.
export function NoRunBadge() {
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 10,
      background: 'var(--surface-2)', color: 'var(--text-subtle)',
    }}>
      SIN CORRIDAS
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

// Botonera de acciones del caso (▶ Correr / ✎ Editar / ⧉ Duplicar / 🗑
// Borrar) -- antes vivía en cada fila de la lista de "Casos", ahora vive acá
// también (ver TestCasesTab.jsx, CaseRowActions) y en el header del detalle,
// agrupada junto a la navegación ▲/▼ y el cierre -- un solo cluster de
// controles arriba a la derecha en vez de dos filas separadas. Iconos con
// tooltip nativo (title) en vez de texto, más compactos.
function CaseActions({ testCase, actions, onClose }) {
  const [rerunning, setRerunning] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleRerun() {
    setRerunning(true)
    try { await actions.onRerun(testCase) } finally { setRerunning(false) }
  }
  async function handleDelete() {
    setDeleting(true)
    try {
      const deleted = await actions.onDelete(testCase)
      if (deleted) onClose()
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
      <button className="btn-primary btn-sm" title="Correr" disabled={rerunning} onClick={handleRerun}>
        {rerunning ? '...' : '▶'}
      </button>
      <button className="btn-ghost btn-sm" title="Editar" onClick={() => { actions.onEdit(testCase); onClose() }}>✎</button>
      <button className="btn-ghost btn-sm" title="Duplicar" onClick={() => { actions.onDuplicate(testCase); onClose() }}>⧉</button>
      <button className="btn-danger btn-sm" title="Borrar" disabled={deleting} onClick={handleDelete}>
        {deleting ? '...' : '🗑'}
      </button>
    </div>
  )
}

export default function CaseResultView({ run, testCase, actions, apiCall, onClose, onNavigate, canPrev, canNext, navigating }) {
  if (!run && !testCase) return null
  const failed = (run?.check_results || []).filter(c => c.kind === 'assert' && !c.passed).length
  const title = testCase?.title || run?.test_case_title

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: 1400, width: '95vw', height: '92vh', display: 'flex', flexDirection: 'column' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            {run ? <StatusBadge status={run.status} failedChecks={failed} /> : <NoRunBadge />}
            <strong style={{ fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {title}
            </strong>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {actions && <CaseActions testCase={testCase} actions={actions} onClose={onClose} />}
            {actions && onNavigate && <div style={{ width: 1, height: 22, background: 'var(--surface-2)' }} />}
            {onNavigate && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <NavButton dir="prev" disabled={!canPrev || navigating} onClick={() => onNavigate('prev')} />
                <NavButton dir="next" disabled={!canNext || navigating} onClick={() => onNavigate('next')} />
              </div>
            )}
            <button className="btn-ghost btn-sm" onClick={onClose} title="Cerrar">✕</button>
          </div>
        </div>

        {testCase && (testCase.description || testCase.turns) && (
          <div style={{ fontSize: 12, color: 'var(--text-subtle)', margin: '8px 0 12px', flexShrink: 0, paddingBottom: 10, borderBottom: '1px solid var(--surface-2)' }}>
            {testCase.turns.length} turno{testCase.turns.length !== 1 ? 's' : ''} · {testCase.checks.length} validación{testCase.checks.length !== 1 ? 'es' : ''}
            {testCase.description ? ` · ${testCase.description}` : ''}
          </div>
        )}

        {!run ? (
          <div className="empty" style={{ padding: '24px 0', flexShrink: 0 }}>
            Este caso todavía no tiene corridas -- probá &quot;▶ Correr&quot; para generar el primer reporte.
          </div>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  )
}
