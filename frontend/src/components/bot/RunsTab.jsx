import { useState, useEffect, useCallback, useMemo } from 'react'
import { humanizeId } from '../../store/flowStore.js'
import { buildStepTree, maxTreeDepth } from '../../utils/stepTree.js'
import FlowExecutionTwin from '../flow/FlowExecutionTwin.jsx'
import { ChatTurn } from './CaseResultView.jsx'
import MonitorPanel from '../MonitorPanel.jsx'

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

const NODO_FLOW_RESERVED_PARAM_KEYS = new Set(['flow_id', 'output', 'routes'])

// Los steps de un run corriendo dentro de un NodoFlow tienen node_id
// namespaceado "${nodoFlowNodeId}::${idDentroDelSubflow}" (posiblemente
// anidado varias veces -- ver lib/flow/expand-node-flows.ts::expandNodeFlows,
// mismo esquema de namespacing). Sin esto, StepRow mostraba ese id crudo en
// vez de la descripción/label del nodo real.
export async function buildNodeLabelMap(nodes, botId, apiCall, prefix, visited) {
  const map = {}
  for (const n of nodes) {
    const id = prefix + n.id
    map[id] = n.label || humanizeId(n.id) || n.type

    const flowId = n.type === 'nodo_flow' ? n.config?.flow_id : null
    if (!flowId || visited.has(flowId)) continue

    const sub = await apiCall('GET', `/flows/bots/${botId}/${flowId}`, null).catch(() => null)
    const innerNodes = sub?.definition?.nodes ?? []
    const subMap = await buildNodeLabelMap(innerNodes, botId, apiCall, `${id}::`, new Set([...visited, flowId]))
    Object.assign(map, subMap)

    // Nodos set_state sintéticos que expandNodeFlows inserta para inyectar
    // los params del NodoFlow -- no existen en la definition, se generan acá
    // con el mismo orden (cfg sin reservados, + "output" al final si hay).
    const cfg = n.config ?? {}
    const paramEntries = Object.keys(cfg).filter(k => !NODO_FLOW_RESERVED_PARAM_KEYS.has(k))
    if (cfg.output) paramEntries.push('output')
    paramEntries.forEach((key, i) => { map[`${id}::__params__${i}`] = `Parámetro: ${key}` })
  }
  return map
}

// Descripción genérica por tipo de nodo (node-types.json, vía el mismo
// endpoint que ya consume FlowExecutionTwin.jsx) -- a diferencia de
// buildNodeLabelMap, esto no depende del flow puntual: un solo fetch alcanza
// para toda la tab.
export async function fetchNodeTypeDescriptions(apiCall) {
  const typeList = await apiCall('GET', '/flows/node-types', null).catch(() => null)
  const map = {}
  for (const t of Array.isArray(typeList) ? typeList : []) {
    if (t?.id) map[t.id] = t.description || ''
  }
  return map
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

// Detalle expandible de un step puntual (conversation acumulada + grid
// input/output) -- reusado tanto por cada nodo del árbol como, potencialmente,
// por cualquier otra vista que necesite el mismo detalle.
function StepDetail({ step }) {
  const conversation = step.output_state?.data?.conversation
  return (
    <div style={{ padding: '10px 12px', background: 'var(--surface-2)' }}>
      {Array.isArray(conversation) && conversation.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-subtle)', marginBottom: 4, letterSpacing: 1 }}>
            CONVERSATION ({conversation.length})
          </div>
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '6px 8px', maxHeight: 160, overflow: 'auto',
          }}>
            <JsonViewer data={conversation} />
          </div>
        </div>
      )}
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
    </div>
  )
}

function stepTreeKey(node) {
  return `${node.id}#${node.step.id}`
}

// Fila de un nodo del árbol de steps -- indentada por profundidad, con su
// propio expand/collapse de hijos (independiente del toggle de detalle
// INPUT/OUTPUT). Sin límite de anidamiento: se llama a sí misma.
function StepTreeNode({ node, nodeLabels, nodeDescriptions, expandedIds, onToggleChildren }) {
  const [detailOpen, setDetailOpen] = useState(false)
  const step = node.step
  const label = nodeLabels?.[step.node_id] || step.node_id
  const description = nodeDescriptions?.[step.node_type]
  const hasChildren = node.children.length > 0
  const key = stepTreeKey(node)
  const childrenVisible = hasChildren && expandedIds.has(key)

  return (
    <div>
      <div
        onClick={() => setDetailOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
          padding: '6px 8px', paddingLeft: 8 + node.depth * 18,
          borderBottom: '1px solid var(--border)', fontSize: 13,
        }}
      >
        {hasChildren ? (
          <span
            onClick={e => { e.stopPropagation(); onToggleChildren(key) }}
            style={{ width: 12, textAlign: 'center', color: 'var(--text-subtle)' }}
          >
            {childrenVisible ? '▾' : '▸'}
          </span>
        ) : <span style={{ width: 12 }} />}
        <span style={{ fontWeight: 500, minWidth: 110 }}>{step.node_type}</span>
        <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--text-muted)' }}>
          {label}
          {description && (
            <div style={{ fontSize: 11, color: 'var(--text-subtle)', fontWeight: 400 }}>{description}</div>
          )}
        </span>
        <span style={{ color: statusColor(step.status), fontWeight: 600, fontSize: 12, width: 80, flexShrink: 0 }}>
          {step.status}
        </span>
        <span style={{ color: 'var(--text-subtle)', fontSize: 12, width: 80, flexShrink: 0 }}>{step.branch_taken ?? '—'}</span>
        <span style={{ color: 'var(--text-subtle)', fontSize: 12, width: 110, flexShrink: 0 }}>{formatDateTime(step.started_at)}</span>
        <span style={{ color: 'var(--text-subtle)', fontSize: 12, width: 55, flexShrink: 0 }}>{duration(step.started_at, step.ended_at)}</span>
      </div>
      {detailOpen && <StepDetail step={step} />}
      {childrenVisible && node.children.map(c => (
        <StepTreeNode
          key={stepTreeKey(c)}
          node={c}
          nodeLabels={nodeLabels}
          nodeDescriptions={nodeDescriptions}
          expandedIds={expandedIds}
          onToggleChildren={onToggleChildren}
        />
      ))}
    </div>
  )
}

// Junta todas las keys cuyos HIJOS deben empezar visibles para un nivel de
// anidamiento dado (0 = todo colapsado, 1 = se ven los sub-nodos de primer
// nivel, etc). Se recalcula cada vez que cambia el filtro de nivel; el
// usuario puede seguir togglear nodos puntuales por encima de este default.
function defaultExpandedForLevel(tree, level, acc) {
  for (const n of tree) {
    if (n.depth < level && n.children.length) {
      acc.add(stepTreeKey(n))
      defaultExpandedForLevel(n.children, level, acc)
    }
  }
  return acc
}

function inRange(iso, from, to) {
  if (!iso) return true
  const t = new Date(iso).getTime()
  if (from && t < new Date(from).getTime()) return false
  if (to && t > new Date(to).getTime()) return false
  return true
}

// Panel de steps de una corrida: filtro de nivel de anidamiento (sin límite
// de profundidad, ver utils/stepTree.js) + filtro de fecha, sobre el árbol
// reconstruido a partir del array plano que ya trae la corrida.
function StepsPanel({ steps, nodeLabels, nodeDescriptions }) {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [levelFilter, setLevelFilter] = useState(null) // null = "todos"

  const filteredSteps = useMemo(
    () => steps.filter(s => inRange(s.started_at, dateFrom, dateTo)),
    [steps, dateFrom, dateTo],
  )
  const tree = useMemo(() => buildStepTree(filteredSteps), [filteredSteps])
  const depth = useMemo(() => maxTreeDepth(tree), [tree])
  const effectiveLevel = levelFilter == null ? depth + 1 : levelFilter

  const [expandedIds, setExpandedIds] = useState(new Set())
  useEffect(() => {
    setExpandedIds(defaultExpandedForLevel(tree, effectiveLevel, new Set()))
  }, [tree, effectiveLevel])

  function toggleChildren(key) {
    setExpandedIds(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8, fontSize: 12, flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', gap: 4, alignItems: 'center', color: 'var(--text-subtle)' }}>
          Desde
          <input type="datetime-local" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            style={{ fontSize: 12 }} />
        </label>
        <label style={{ display: 'flex', gap: 4, alignItems: 'center', color: 'var(--text-subtle)' }}>
          Hasta
          <input type="datetime-local" value={dateTo} onChange={e => setDateTo(e.target.value)}
            style={{ fontSize: 12 }} />
        </label>
        {depth > 0 && (
          <label style={{ display: 'flex', gap: 4, alignItems: 'center', color: 'var(--text-subtle)' }}>
            Nivel
            <select value={levelFilter == null ? 'all' : levelFilter}
              onChange={e => setLevelFilter(e.target.value === 'all' ? null : Number(e.target.value))}
              style={{ fontSize: 12 }}>
              <option value="all">Todos ({depth + 1})</option>
              {Array.from({ length: depth + 1 }, (_, i) => (
                <option key={i} value={i}>Hasta nivel {i}</option>
              ))}
            </select>
          </label>
        )}
        {(dateFrom || dateTo) && (
          <button className="btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => { setDateFrom(''); setDateTo('') }}>
            ✕ Limpiar fechas
          </button>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, padding: '4px 8px', paddingLeft: 8, fontSize: 11, fontWeight: 600, color: 'var(--text-subtle)', borderBottom: '1px solid var(--border)' }}>
        <span style={{ width: 12 }} />
        <span style={{ minWidth: 110 }}>Tipo</span>
        <span style={{ flex: 1 }}>Nodo</span>
        <span style={{ width: 80 }}>Status</span>
        <span style={{ width: 80 }}>Rama</span>
        <span style={{ width: 110 }}>Inicio</span>
        <span style={{ width: 55 }}>Tiempo</span>
      </div>

      {tree.length === 0
        ? <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-subtle)', fontSize: 13 }}>Sin steps</div>
        : tree.map(n => (
          <StepTreeNode
            key={stepTreeKey(n)}
            node={n}
            nodeLabels={nodeLabels}
            nodeDescriptions={nodeDescriptions}
            expandedIds={expandedIds}
            onToggleChildren={toggleChildren}
          />
        ))
      }
    </div>
  )
}

function RunDetail({ run, onClose, botId, apiCall }) {
  const trigger = run.trigger_data ?? {}
  // El mensaje que disparó el run vive en conversation[0] (ver graphs/conversation.py);
  // trigger.message solo existe como fallback en runs viejos o sin conversación.
  const firstMessage = trigger.data?.conversation?.[0]?.content ?? trigger.message
  const [nodeLabels, setNodeLabels] = useState({})
  const [nodeDescriptions, setNodeDescriptions] = useState({})

  // La conversación completa de la corrida vive en el output_state del
  // último step (se va acumulando step a step, ver web/lib/nodes/state.ts::
  // appendConversationEntry) -- trigger.data.conversation solo tiene el
  // primer mensaje que disparó el run.
  const steps = run.steps ?? []
  const conversation = steps.length
    ? (steps[steps.length - 1].output_state?.data?.conversation ?? trigger.data?.conversation ?? [])
    : (trigger.data?.conversation ?? [])
  // ChatTurn (bot/CaseResultView.jsx, reusado tal cual acá) espera
  // {role: 'user'|'bot', text} -- ConversationEntry (web/lib/nodes/state.ts)
  // usa {origin: 'user'|'bot_reply', content}.
  const turns = conversation.map(c => ({ role: c.origin === 'user' ? 'user' : 'bot', text: c.content }))

  const [flowSnapshot, setFlowSnapshot] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiCall('GET', `/flows/bots/${botId}/${run.flow_id}`, null)
      .then(flow => {
        if (cancelled || !flow?.definition?.nodes) return
        setFlowSnapshot(flow.definition)
        return buildNodeLabelMap(flow.definition.nodes, botId, apiCall, '', new Set())
      })
      .then(map => { if (!cancelled && map) setNodeLabels(map) })
      .catch(() => {})
    fetchNodeTypeDescriptions(apiCall).then(map => { if (!cancelled) setNodeDescriptions(map) })
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

      {/* Cuadrantes -- mismo patrón split que CaseResultView.jsx (Tests):
          conversación reproducida a la izquierda, flow real con el camino
          recorrido resaltado a la derecha (definición EN VIVO del flow, no
          un snapshot -- si el flow cambió desde esta corrida, el diagrama
          puede no calzar 1:1). */}
      <div style={{ display: 'flex', gap: 16, height: 360, marginBottom: 16 }}>
        <div style={{ flex: '1 1 50%', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8, flexShrink: 0 }}>
            CONVERSACIÓN {turns.length > 0 && `(${turns.length})`}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, border: '1px solid var(--surface-2)', borderRadius: 8, padding: '8px 12px' }}>
            {turns.length > 0
              ? turns.map((t, i) => <ChatTurn key={i} turn={t} />)
              : <div style={{ fontSize: 12, color: 'var(--text-subtle)' }}>Sin conversación registrada para esta corrida.</div>}
          </div>
        </div>
        <div style={{ flex: '1 1 50%', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)', marginBottom: 8, flexShrink: 0 }}>
            FLOW (definición en vivo — camino recorrido resaltado)
          </div>
          <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
            {flowSnapshot
              ? <FlowExecutionTwin flowSnapshot={flowSnapshot} steps={steps} apiCall={apiCall} />
              : <div className="empty" style={{ padding: '16px 0' }}>Cargando flow…</div>}
          </div>
        </div>
      </div>

      <details style={{ marginBottom: 14 }}>
        <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)' }}>
          trigger_data (JSON completo)
        </summary>
        <div style={{
          overflow: 'auto', maxHeight: 300,
          border: '1px solid var(--border)', borderRadius: 6,
          marginTop: 6, background: 'var(--surface)', padding: '4px 0',
        }}>
          <JsonViewer data={trigger} />
        </div>
      </details>

      <StepsPanel steps={steps} nodeLabels={nodeLabels} nodeDescriptions={nodeDescriptions} />
    </div>
  )
}

export default function RunsTab({ botId, apiCall }) {
  const [runs, setRuns]       = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  // Monitor de esta bot, colapsable arriba de la lista -- arrastrar un rango
  // sobre su gráfico precarga estos mismos since/until (ver
  // MonitorPanel.jsx::OverlapChart, onRangeSelect).
  const [monitorOpen, setMonitorOpen] = useState(false)

  function handleMonitorRangeSelect(fromIso, toIso) {
    setSince(fromIso.slice(0, 16))
    setUntil(toIso.slice(0, 16))
  }

  const load = useCallback(async () => {
    const qs = new URLSearchParams({ limit: '30' })
    if (since) qs.set('since', new Date(since).toISOString())
    if (until) qs.set('until', new Date(until).toISOString())
    const data = await apiCall('GET', `/runs/bots/${botId}?${qs}`, null).catch(() => null)
    if (Array.isArray(data)) setRuns(data)
  }, [botId, apiCall, since, until])

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
      <div style={{ border: '1px solid var(--border)', borderRadius: 6, marginBottom: 14 }}>
        <div
          onClick={() => setMonitorOpen(o => !o)}
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '8px 10px', cursor: 'pointer',
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-subtle)' }}>📊 Monitor</span>
          <span style={{ fontSize: 11, color: 'var(--text-subtle)' }}>{monitorOpen ? '▲ Colapsar' : '▼ Expandir'}</span>
        </div>
        {monitorOpen && (
          <div style={{ padding: '0 10px 10px' }}>
            <MonitorPanel botId={botId} active={monitorOpen} onRangeSelect={handleMonitorRangeSelect} />
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--text-subtle)' }}>
          {runs.length === 0 ? 'Sin ejecuciones' : `${runs.length} ejecuciones recientes`}
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
          <label style={{ display: 'flex', gap: 4, alignItems: 'center', color: 'var(--text-subtle)' }}>
            Desde
            <input type="datetime-local" value={since} onChange={e => setSince(e.target.value)} style={{ fontSize: 12 }} />
          </label>
          <label style={{ display: 'flex', gap: 4, alignItems: 'center', color: 'var(--text-subtle)' }}>
            Hasta
            <input type="datetime-local" value={until} onChange={e => setUntil(e.target.value)} style={{ fontSize: 12 }} />
          </label>
          {(since || until) && (
            <button className="btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => { setSince(''); setUntil('') }}>
              ✕ Limpiar
            </button>
          )}
          <button className="btn-ghost btn-sm" onClick={load}>↺ Actualizar</button>
        </div>
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
