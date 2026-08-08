/**
 * Tab "Test": suite de tests e2e configurable 100% desde la UI, sin código
 * ni pytest -- reemplaza TestReportsTab.jsx (reportes HTML estáticos
 * generados por scripts/generate_e2e_report.py).
 *
 * Una sola vista, "Casos": CRUD de test_cases (turnos de conversación +
 * validaciones, ambos como builders estructurados -- ver
 * web/lib/business/test-checks.ts para la definición canónica de CheckSpec,
 * CHECK_TYPES acá abajo es un espejo en JS de ese mismo archivo, mantenerlos
 * en sync a mano). Los resultados de la última corrida de cada caso viven
 * integrados en esta misma lista (badge de estado) y en el detalle
 * (CaseResultView) -- no hay una vista de "Resultados" separada.
 *
 * El motor de ejecución corre in-process dentro de `web/` (sin pytest, sin
 * gastar cuota de Vercel Workflow -- ver web/lib/business/test-runner.ts) --
 * "▶ Correr" acá es literalmente un POST que devuelve el resultado ya
 * persistido.
 */
import { useEffect, useState, useCallback } from 'react'
import CaseResultView, { StatusBadge, NoRunBadge } from './CaseResultView.jsx'
import TestReportPublishModal from '../TestReportPublishModal.jsx'

// Fetch usado tanto al abrir "Ver" por primera vez como al navegar entre
// casos con las flechas ▲/▼ de CaseResultView.
const fetchLatestRunForCase = (apiCall, botId, caseId) =>
  apiCall('GET', `/bots/${botId}/test-cases/${caseId}/latest-run`, null).catch(() => null)

// Índice destino al navegar con ▲/▼ en CaseResultView, o null si el
// movimiento se sale de la lista (flecha debe quedar deshabilitada ahí).
export function computeNavIndex(index, idsLength, direction) {
  const newIndex = direction === 'prev' ? index - 1 : index + 1
  return newIndex < 0 || newIndex >= idsLength ? null : newIndex
}

// Espejo de CHECK_TYPES en web/lib/business/test-checks.ts -- mismo orden,
// mismos `type`, mismo criterio needsNode. Si se agrega un tipo de check
// ahí, agregarlo acá también.
const CHECK_TYPES = [
  { type: 'ran_node', label: 'El nodo corrió', needsNode: true },
  { type: 'branch_taken', label: 'Rama tomada en un nodo condición/router', needsNode: true },
  { type: 'state_field', label: 'Campo del estado (igual / contiene / no vacío)', needsNode: true },
  { type: 'min_fetch_results', label: 'Cantidad mínima de resultados de un fetch', needsNode: true },
  { type: 'reply_not_empty', label: 'El bot respondió (no vacío)', needsNode: false },
  { type: 'no_unresolved_templates', label: 'Sin placeholders {{...}} sin resolver', needsNode: false },
  { type: 'no_fetch_errors', label: 'Sin fetch HTTP fallidos', needsNode: false },
  { type: 'no_llm_errors', label: 'Sin contenido vacío persistente de un LLM', needsNode: false },
  { type: 'no_node_errors', label: 'Ningún nodo crasheó', needsNode: false },
  { type: 'reached_end_conversation', label: 'Llegó a un end_conversation real', needsNode: false },
  { type: 'no_separator_leak', label: 'Sin fuga del separador técnico "|||"', needsNode: false },
]

function defaultCheck(type) {
  const meta = CHECK_TYPES.find(c => c.type === type)
  const base = { type, kind: 'assert', label: meta?.label || type }
  if (type === 'ran_node') return { ...base, nodeId: '', status: 'ok', occurrence: -1 }
  if (type === 'branch_taken') return { ...base, nodeId: '', expected: '', occurrence: -1 }
  if (type === 'state_field') return { ...base, nodeId: '', key: '', operator: 'not_empty', value: '', occurrence: -1 }
  if (type === 'min_fetch_results') return { ...base, nodeId: '', field: '', min: 1 }
  if (type === 'no_separator_leak') return { ...base, separator: '|||' }
  return base
}

function emptyForm() {
  return { chat_config_id: '', slug: '', title: '', description: '', turns: [{ message: '' }], checks: [] }
}

// ─── Editor de un check (fila del builder) ──────────────────────────────

function CheckRow({ check, nodes, onChange, onRemove }) {
  const meta = CHECK_TYPES.find(c => c.type === check.type)
  function set(patch) { onChange({ ...check, ...patch }) }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 10px',
      border: '1px solid var(--border)', borderRadius: 8, background: 'var(--surface-2)',
    }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <select
          value={check.type}
          onChange={e => onChange(defaultCheck(e.target.value))}
          style={{ flex: 1 }}
        >
          {CHECK_TYPES.map(c => <option key={c.type} value={c.type}>{c.label}</option>)}
        </select>
        <select value={check.kind} onChange={e => set({ kind: e.target.value })} style={{ width: 110 }}>
          <option value="assert">assert</option>
          <option value="log">log</option>
        </select>
        <button type="button" className="btn-danger btn-sm" onClick={onRemove}>✕</button>
      </div>

      <input
        placeholder="Label (descripción de la validación)"
        value={check.label || ''}
        onChange={e => set({ label: e.target.value })}
        style={{ width: '100%' }}
      />

      {meta?.needsNode && (
        <select value={check.nodeId || ''} onChange={e => set({ nodeId: e.target.value })}>
          <option value="">-- elegir nodo --</option>
          {nodes.map(n => <option key={n.id} value={n.id}>{n.id} ({n.type})</option>)}
        </select>
      )}

      {check.type === 'ran_node' && (
        <div style={{ display: 'flex', gap: 6 }}>
          <input placeholder="status (default ok)" value={check.status || ''} onChange={e => set({ status: e.target.value })} style={{ flex: 1 }} />
          <input type="number" placeholder="occurrence (-1 = última)" value={check.occurrence ?? -1}
            onChange={e => set({ occurrence: Number(e.target.value) })} style={{ width: 160 }} />
        </div>
      )}

      {check.type === 'branch_taken' && (
        <div style={{ display: 'flex', gap: 6 }}>
          <input placeholder="rama esperada (vacío = cualquiera)" value={check.expected || ''} onChange={e => set({ expected: e.target.value })} style={{ flex: 1 }} />
          <input type="number" placeholder="occurrence (-1 = última)" value={check.occurrence ?? -1}
            onChange={e => set({ occurrence: Number(e.target.value) })} style={{ width: 160 }} />
        </div>
      )}

      {check.type === 'state_field' && (
        <>
          <div style={{ display: 'flex', gap: 6 }}>
            <input placeholder="key (ej. necesidad)" value={check.key || ''} onChange={e => set({ key: e.target.value })} style={{ flex: 1 }} />
            <select value={check.operator} onChange={e => set({ operator: e.target.value })} style={{ width: 130 }}>
              <option value="equals">equals</option>
              <option value="contains">contains</option>
              <option value="not_empty">not_empty</option>
            </select>
          </div>
          {check.operator !== 'not_empty' && (
            <input placeholder="valor esperado" value={check.value || ''} onChange={e => set({ value: e.target.value })} style={{ width: '100%' }} />
          )}
          <input type="number" placeholder="occurrence (-1 = última)" value={check.occurrence ?? -1}
            onChange={e => set({ occurrence: Number(e.target.value) })} style={{ width: 160 }} />
        </>
      )}

      {check.type === 'min_fetch_results' && (
        <div style={{ display: 'flex', gap: 6 }}>
          <input placeholder="field (ej. context)" value={check.field || ''} onChange={e => set({ field: e.target.value })} style={{ flex: 1 }} />
          <input type="number" placeholder="mínimo" value={check.min ?? 1} onChange={e => set({ min: Number(e.target.value) })} style={{ width: 100 }} />
        </div>
      )}

      {check.type === 'no_separator_leak' && (
        <input placeholder="separador (default |||)" value={check.separator || ''} onChange={e => set({ separator: e.target.value })} style={{ width: '100%' }} />
      )}
    </div>
  )
}

// ─── Editor de caso (modal) ──────────────────────────────────────────────

function CaseForm({ botId, apiCall, testCase, onClose, onSaved }) {
  const isNew = !testCase
  const [chatConfigs, setChatConfigs] = useState([])
  const [nodes, setNodes] = useState([])
  const [form, setForm] = useState(() => testCase ? {
    chat_config_id: testCase.chat_config_id, slug: testCase.slug, title: testCase.title,
    description: testCase.description || '', turns: testCase.turns.length ? testCase.turns : [{ message: '' }],
    checks: testCase.checks,
  } : emptyForm())
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    apiCall('GET', `/bots/${botId}/chat-configs`, null).then(d => setChatConfigs(Array.isArray(d) ? d : [])).catch(() => {})
  }, [botId, apiCall])

  useEffect(() => {
    const cfg = chatConfigs.find(c => c.id === form.chat_config_id)
    if (!cfg) { setNodes([]); return }
    let cancelled = false
    apiCall('GET', `/flows/bots/${botId}/${cfg.flow_id}`, null).then(full => {
      if (cancelled) return
      setNodes(full?.definition?.nodes ?? [])
    }).catch(() => {})
    return () => { cancelled = true }
  }, [botId, form.chat_config_id, chatConfigs, apiCall])

  function updateField(key, value) { setForm(f => ({ ...f, [key]: value })) }

  function updateTurn(i, message) {
    setForm(f => ({ ...f, turns: f.turns.map((t, idx) => idx === i ? { message } : t) }))
  }
  function addTurn() { setForm(f => ({ ...f, turns: [...f.turns, { message: '' }] })) }
  function removeTurn(i) { setForm(f => ({ ...f, turns: f.turns.filter((_, idx) => idx !== i) })) }
  function moveTurn(i, dir) {
    setForm(f => {
      const turns = [...f.turns]
      const j = i + dir
      if (j < 0 || j >= turns.length) return f
      ;[turns[i], turns[j]] = [turns[j], turns[i]]
      return { ...f, turns }
    })
  }

  function addCheck() { setForm(f => ({ ...f, checks: [...f.checks, defaultCheck('reply_not_empty')] })) }
  function updateCheck(i, next) { setForm(f => ({ ...f, checks: f.checks.map((c, idx) => idx === i ? next : c) })) }
  function removeCheck(i) { setForm(f => ({ ...f, checks: f.checks.filter((_, idx) => idx !== i) })) }

  async function handleSubmit(e) {
    e.preventDefault()
    setErr('')
    if (!form.chat_config_id) { setErr('Elegí contra qué chat de prueba correr'); return }
    if (!form.slug.trim()) { setErr('Falta el slug'); return }
    if (!form.title.trim()) { setErr('Falta el título'); return }
    if (form.turns.some(t => !t.message.trim())) { setErr('Todos los turnos necesitan un mensaje'); return }

    setSaving(true)
    const res = isNew
      ? await apiCall('POST', `/bots/${botId}/test-cases`, form).catch(() => null)
      : await apiCall('PUT', `/bots/${botId}/test-cases/${testCase.id}`, form).catch(() => null)
    setSaving(false)
    if (!res?.id) { setErr(res?.detail || res?.error || 'Error al guardar'); return }
    onSaved?.(res)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 640, maxHeight: '88vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <strong>{isNew ? 'Nuevo caso de test' : 'Editar caso de test'}</strong>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ fontSize: 13 }}>
            Título
            <input value={form.title} onChange={e => updateField('title', e.target.value)} style={{ width: '100%', marginTop: 4 }} />
          </label>

          <label style={{ fontSize: 13 }}>
            Slug (id estable, sin espacios)
            <input value={form.slug} onChange={e => updateField('slug', e.target.value)} style={{ width: '100%', marginTop: 4 }} />
          </label>

          <label style={{ fontSize: 13 }}>
            Descripción
            <textarea value={form.description} onChange={e => updateField('description', e.target.value)}
              rows={2} style={{ width: '100%', marginTop: 4 }} />
          </label>

          <label style={{ fontSize: 13 }}>
            Chat de prueba (flow + trigger contra el que corre)
            <select value={form.chat_config_id} onChange={e => updateField('chat_config_id', e.target.value)} style={{ width: '100%', marginTop: 4 }}>
              <option value="">-- elegir --</option>
              {chatConfigs.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          </label>

          <div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Turnos de la conversación</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {form.turns.map((t, i) => (
                <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-subtle)', width: 18, marginTop: 8 }}>{i + 1}</span>
                  <textarea
                    value={t.message} onChange={e => updateTurn(i, e.target.value)}
                    placeholder="Lo que manda el usuario en este turno"
                    rows={2} style={{ flex: 1 }}
                  />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <button type="button" className="btn-ghost btn-sm" disabled={i === 0} onClick={() => moveTurn(i, -1)}>↑</button>
                    <button type="button" className="btn-ghost btn-sm" disabled={i === form.turns.length - 1} onClick={() => moveTurn(i, 1)}>↓</button>
                    <button type="button" className="btn-danger btn-sm" onClick={() => removeTurn(i)}>✕</button>
                  </div>
                </div>
              ))}
            </div>
            <button type="button" className="btn-sm" style={{ marginTop: 6 }} onClick={addTurn}>+ Turno</button>
          </div>

          <div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Validaciones</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {form.checks.map((c, i) => (
                <CheckRow key={i} check={c} nodes={nodes} onChange={next => updateCheck(i, next)} onRemove={() => removeCheck(i)} />
              ))}
            </div>
            <button type="button" className="btn-sm" style={{ marginTop: 6 }} onClick={addCheck}>+ Validación</button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button type="submit" className="btn-primary btn-sm" disabled={saving}>
              {saving ? 'Guardando...' : isNew ? 'Crear caso' : 'Guardar cambios'}
            </button>
            {err && <span style={{ color: 'var(--danger)', fontSize: 13 }}>{err}</span>}
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Vista "Casos" ────────────────────────────────────────────────────────

// Botonera de una fila de la lista (▶ Correr / ✎ Editar / ⧉ Duplicar / 🗑
// Borrar) -- mismos botones que en el header del detalle, ahora también acá
// a la izquierda del badge de estado. Sin el ojo: el click en la fila entera
// ya abre el reporte, no hace falta un botón dedicado a "ver".
function CaseRowActions({ testCase, onRun, onEdit, onDuplicate, onDelete }) {
  const [running, setRunning] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleRun(e) {
    e.stopPropagation()
    setRunning(true)
    try { await onRun(testCase) } finally { setRunning(false) }
  }
  async function handleDelete(e) {
    e.stopPropagation()
    setDeleting(true)
    try { await onDelete(testCase) } finally { setDeleting(false) }
  }

  return (
    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
      <button className="btn-primary btn-sm" title="Correr" disabled={running} onClick={handleRun}>
        {running ? '...' : '▶'}
      </button>
      <button className="btn-ghost btn-sm" title="Editar" onClick={() => onEdit(testCase)}>✎</button>
      <button className="btn-ghost btn-sm" title="Duplicar" onClick={() => onDuplicate(testCase)}>⧉</button>
      <button className="btn-danger btn-sm" title="Borrar" disabled={deleting} onClick={handleDelete}>
        {deleting ? '...' : '🗑'}
      </button>
    </div>
  )
}

function CasesView({ botId, apiCall, onViewRun }) {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null) // null=cerrado, {}=nuevo, case=editar
  const [running, setRunning] = useState(null) // 'ALL' mientras corre "Correr todos"
  const [opening, setOpening] = useState(null) // caseId cuyo detalle se está por abrir
  const [publishOpen, setPublishOpen] = useState(false)
  const [keyBusy, setKeyBusy] = useState(false)
  const [keyCopied, setKeyCopied] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiCall('GET', `/bots/${botId}/test-cases`, null).catch(() => null)
      if (Array.isArray(data)) setCases(data)
    } finally {
      setLoading(false)
    }
  }, [botId, apiCall])

  useEffect(() => { load() }, [load])

  // Retorna true si se borró de verdad -- CaseResultView usa el resultado
  // para saber si tiene que cerrarse (si el usuario cancela el confirm,
  // el detalle se queda abierto).
  async function handleDelete(c) {
    if (!confirm(`¿Borrar el caso "${c.title}"?`)) return false
    await apiCall('DELETE', `/bots/${botId}/test-cases/${c.id}`, null).catch(() => {})
    load()
    return true
  }

  function handleDuplicate(c) {
    setEditing({ ...c, id: undefined, slug: `${c.slug}-copia`, title: `${c.title} (copia)` })
  }

  // Re-ejecución disparada desde adentro del detalle (CaseResultView) --
  // actualiza el reporte in place, sin cambiar de tab. La respuesta del POST
  // ya trae el run completo (steps + flow_snapshot), no hace falta refetch.
  async function handleRerun(c) {
    const result = await apiCall('POST', `/bots/${botId}/test-cases/${c.id}/run`, null).catch(() => null)
    if (result?.id) onViewRun(v => v ? { ...v, run: result } : v)
    load() // refresca el badge de la lista con el nuevo estado
    return result
  }

  async function handleRunAll() {
    setRunning('ALL')
    try {
      await apiCall('POST', `/bots/${botId}/test-runs`, {}).catch(() => null)
    } finally {
      setRunning(null)
      load()
    }
  }

  // Arma y copia el link del reporte público con la clave del bot (mismo
  // secreto `bots.apiKey`/`X-Pulpo-Bot-Key` que ya usa la integración de
  // publicidad de chat, ver ChatAdsPanel.jsx::IntegrationsSection) -- si
  // todavía no existe, la genera. La clave solo se puede leer en el momento
  // en que se genera (no se vuelve a mostrar), así que regenerarla acá
  // invalida la que ya tenga configurada esa otra integración, si la hay.
  async function handleCopyKeyLink() {
    setKeyBusy(true)
    setKeyCopied(false)
    try {
      const bot = await apiCall('GET', `/bots/${botId}`, null).catch(() => null)
      let key = null
      if (!bot?.has_api_key) {
        const res = await apiCall('POST', `/bots/${botId}/api-key`, {}).catch(() => null)
        key = res?.api_key || null
      }
      if (!key) {
        alert('La clave de este bot ya fue generada antes y no se puede volver a leer -- regenerala desde "Chats" > "Integraciones" para conseguir un link nuevo.')
        return
      }
      const link = `${window.location.origin}/embed/test-reports/${botId}?key=${key}`
      await navigator.clipboard.writeText(link)
      setKeyCopied(true)
      setTimeout(() => setKeyCopied(false), 2000)
    } finally {
      setKeyBusy(false)
    }
  }

  // Abre el detalle directo desde el click en la fila -- toda la línea es
  // el CTA (ver comentario de arriba del archivo). Si el caso todavía no
  // tiene corridas, el detalle igual abre con un estado vacío.
  async function handleOpen(c) {
    setOpening(c.id)
    try {
      const run = await fetchLatestRunForCase(apiCall, botId, c.id)
      onViewRun({
        run: run?.id ? run : null,
        testCase: c,
        kind: 'case',
        ids: cases.map(x => x.id),
        cases,
        index: cases.findIndex(x => x.id === c.id),
        actions: { onRerun: handleRerun, onEdit: setEditing, onDuplicate: handleDuplicate, onDelete: handleDelete },
      })
    } finally {
      setOpening(null)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--text-subtle)' }}>
          {cases.length === 0 ? 'Sin casos de test' : `${cases.length} caso${cases.length !== 1 ? 's' : ''}`}
        </span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <a
            href={`/embed/test-reports/${botId}`}
            target="_blank"
            rel="noreferrer"
            className="btn-ghost btn-sm"
            title="Vista pública de todos los reportes publicados, sin botones -- para compartir con el cliente"
          >
            Ver reportes públicos ↗
          </a>
          <button className="btn-ghost btn-sm" disabled={!cases.some(c => c.latest_run)} onClick={() => setPublishOpen(true)}>
            Publicar
          </button>
          <button
            className="btn-ghost btn-sm"
            disabled={keyBusy}
            title="Copia el link de reportes públicos con la clave del bot -- para compartir con un tercero (ej. el sitio del cliente) sin darle acceso al dashboard"
            onClick={handleCopyKeyLink}
          >
            {keyCopied ? '✓ Copiado' : keyBusy ? 'Generando...' : '🔑 Copiar link con clave'}
          </button>
          <button className="btn-ghost btn-sm" onClick={() => setEditing({})}>+ Nuevo caso</button>
          <button className="btn-primary btn-sm" disabled={!cases.length || running === 'ALL'} onClick={handleRunAll}>
            {running === 'ALL' ? 'Corriendo...' : '▶ Correr todos'}
          </button>
        </div>
      </div>

      <TestReportPublishModal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        apiCall={apiCall}
        botId={botId}
      />

      {loading ? (
        <div className="empty" style={{ padding: '24px 0' }}>Cargando casos...</div>
      ) : cases.length === 0 ? (
        <div className="empty" style={{ padding: '24px 0' }}>Sin casos de test todavía. Creá el primero con &quot;+ Nuevo caso&quot;.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {cases.map(c => (
            <div
              key={c.id}
              onClick={() => handleOpen(c)}
              role="button"
              tabIndex={0}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', cursor: 'pointer',
                background: 'var(--bg)', borderRadius: 8, border: '1px solid var(--surface-2)',
                opacity: opening === c.id ? 0.6 : 1,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{c.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-subtle)', marginTop: 2 }}>
                  {c.turns.length} turno{c.turns.length !== 1 ? 's' : ''} · {c.checks.length} validación{c.checks.length !== 1 ? 'es' : ''}
                  {c.description ? ` · ${c.description}` : ''}
                </div>
              </div>
              <CaseRowActions
                testCase={c} onRun={handleRerun} onEdit={setEditing}
                onDuplicate={handleDuplicate} onDelete={handleDelete}
              />
              {c.latest_run
                ? <StatusBadge status={c.latest_run.status} failedChecks={c.latest_run.failed_checks} />
                : <NoRunBadge />}
            </div>
          ))}
        </div>
      )}

      {editing && (
        <CaseForm
          botId={botId} apiCall={apiCall}
          testCase={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load() }}
        />
      )}
    </div>
  )
}

// ─── Componente raíz de la tab ────────────────────────────────────────────

export default function TestCasesTab({ botId, apiCall }) {
  // corrida completa (con steps + flow_snapshot) abierta en "Ver", más la
  // lista de ids hermanos (casos) y el índice actual dentro de esa lista --
  // lo que habilita las flechas ▲/▼.
  const [viewer, setViewer] = useState(null) // { run, kind: 'case', ids, index }
  const [navigating, setNavigating] = useState(false)

  // Navega entre casos vecinos en el detalle abierto desde "Casos" -- si el
  // caso vecino no tiene corridas, CaseResultView ya sabe mostrar el estado
  // vacío, así que solo se actualiza testCase + run (o null).
  async function handleNavigate(direction) {
    if (!viewer) return
    const newIndex = computeNavIndex(viewer.index, viewer.ids.length, direction)
    if (newIndex === null) return
    setNavigating(true)
    try {
      const run = await fetchLatestRunForCase(apiCall, botId, viewer.ids[newIndex])
      setViewer(v => ({ ...v, run: run?.id ? run : null, testCase: v.cases[newIndex], index: newIndex }))
    } finally {
      setNavigating(false)
    }
  }

  return (
    <div className="ec-config-tab">
      <CasesView botId={botId} apiCall={apiCall} onViewRun={setViewer} />

      {viewer && (
        <CaseResultView
          run={viewer.run}
          testCase={viewer.testCase}
          actions={viewer.actions}
          apiCall={apiCall}
          onClose={() => setViewer(null)}
          onNavigate={handleNavigate}
          canPrev={viewer.index > 0}
          canNext={viewer.index < viewer.ids.length - 1}
          navigating={navigating}
        />
      )}
    </div>
  )
}
