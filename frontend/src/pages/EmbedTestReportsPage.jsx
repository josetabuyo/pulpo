/**
 * Vista pública de reportes de test publicados -- link aparte (sin login,
 * sin botones) que se le comparte al cliente para que vea qué se testea y
 * los resultados, uno debajo del otro, del más reciente al más viejo. Mismo
 * espíritu "solo view" que EmbedFlowPage/EmbedTestRunPage, pero acá NO es
 * headless (no señaliza window.__flowReady) -- esta la abre una persona.
 *
 * Ruta: /embed/test-reports/:botId
 *
 * Fuente: GET /api/test-reports/bots/:botId (público, ver proxy.ts ->
 * TEST_REPORTS_PUBLIC_GET_RE) -- cada fila viene de
 * lib/business/test-report-publish.ts, un snapshot self-contained (no
 * depende de que test_runs siga existiendo).
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

function StatusPill({ status, failedChecks }) {
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

function TestRunCard({ run }) {
  const failed = (run.check_results || []).filter(c => c.kind === 'assert' && !c.passed).length
  return (
    <div style={{
      border: '1px solid var(--surface-2)', borderRadius: 10, padding: 14,
      background: 'var(--bg)', display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusPill status={run.status} failedChecks={failed} />
        <strong style={{ fontSize: 13 }}>{run.test_case_title}</strong>
      </div>
      {run.error_message && <div style={{ color: 'var(--danger)', fontSize: 12 }}>{run.error_message}</div>}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 320px', minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 6 }}>CONVERSACIÓN</div>
          {(run.turns || []).map((t, i) => <ChatTurn key={i} turn={t} />)}
        </div>
        <div style={{ flex: '1 1 260px', minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 6 }}>VALIDACIONES</div>
          {(run.check_results || []).length
            ? run.check_results.map((c, i) => <CheckResultRow key={i} check={c} />)
            : <div style={{ fontSize: 12, color: 'var(--text-subtle)' }}>Sin validaciones configuradas.</div>}
        </div>
        {run.diagram_image && (
          <div style={{ flex: '0 0 auto' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 6 }}>FLOW</div>
            <img src={run.diagram_image} alt="Camino recorrido" style={{ maxWidth: 260, borderRadius: 6, border: '1px solid var(--surface-2)' }} />
          </div>
        )}
      </div>
    </div>
  )
}

function ReportCard({ report }) {
  const { summary } = report
  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 12, padding: 18,
      background: 'var(--surface)', display: 'flex', flexDirection: 'column', gap: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <strong style={{ fontSize: 15 }}>
          {report.published_at ? new Date(report.published_at).toLocaleString('es-AR') : 'Reporte'}
        </strong>
        <span style={{ fontSize: 12, color: 'var(--text-subtle)' }}>
          {summary?.passed}/{summary?.total} pasaron
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {(report.runs || []).map((run, i) => <TestRunCard key={run.id || i} run={run} />)}
      </div>
    </div>
  )
}

export default function EmbedTestReportsPage() {
  const { botId } = useParams()
  const [reports, setReports] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/test-reports/bots/${botId}`, { signal: controller.signal })
      .then(res => { if (!res.ok) throw new Error(`GET /test-reports/bots/${botId} → ${res.status}`); return res.json() })
      .then(data => setReports(Array.isArray(data) ? data : []))
      .catch(e => { if (e.name !== 'AbortError') setError(e.message) })
    return () => controller.abort()
  }, [botId])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', padding: '32px 16px' }}>
      <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div>
          <h2 style={{ margin: 0 }}>Reportes de test</h2>
          <p style={{ color: 'var(--text-subtle)', fontSize: 13, margin: '4px 0 0' }}>
            Resultados publicados de las pruebas automáticas del bot, del más reciente al más viejo.
          </p>
        </div>

        {error && <div style={{ color: 'var(--danger)', fontSize: 13 }}>Error cargando los reportes: {error}</div>}
        {!error && reports === null && <div style={{ color: 'var(--text-subtle)', fontSize: 13 }}>Cargando...</div>}
        {!error && reports?.length === 0 && (
          <div style={{ color: 'var(--text-subtle)', fontSize: 13 }}>Todavía no hay reportes publicados para este bot.</div>
        )}

        {reports?.map(report => <ReportCard key={report.id} report={report} />)}
      </div>
    </div>
  )
}
