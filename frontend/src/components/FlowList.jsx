/**
 * FlowList — lista de flows de una bot con acciones CRUD.
 *
 * Estados:
 *   - list: muestra la tabla de flows + botón "Nuevo flow"
 *   - editor: renderiza FlowEditor para el flow seleccionado
 *
 * La lista se divide en "Activos" (siempre visibles) y "Guardados"
 * (inactivos, colapsados por defecto detrás de un botón contador).
 */
import { useState, useEffect, useCallback } from 'react'
import FlowEditor from './FlowEditor.jsx'

const CONNECTION_LABELS = { telegram: 'TG' }

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

export default function FlowList({ botId, apiCall, connections, onGoToUIs }) {
  const [flows,    setFlows]    = useState([])
  const [loading,  setLoading]  = useState(true)
  const [typeMap,  setTypeMap]  = useState({})
  const [editing,  setEditing]  = useState(null)   // flow completo (con definition)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [savedExpanded, setSavedExpanded] = useState(false)

  const loadFlows = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiCall('GET', `/flows/bots/${botId}`, null)
      if (Array.isArray(data)) setFlows(data)
    } finally {
      setLoading(false)
    }
  }, [botId, apiCall])

  // Cargar tipos de nodo una vez (necesarios para el editor)
  useEffect(() => {
    apiCall('GET', '/flows/node-types', null)
      .then(list => {
        if (Array.isArray(list)) {
          setTypeMap(Object.fromEntries(list.map(t => [t.id, t])))
        }
      })
      .catch(() => {})
  }, [apiCall])

  useEffect(() => { loadFlows() }, [loadFlows])

  async function handleNew(flowKind) {
    setCreating(true)
    try {
      const definition = {
        nodes: [],
        edges: [],
        viewport: { x: 0, y: 0, zoom: 1 },
      }
      const newFlow = await apiCall('POST', `/flows/bots/${botId}`, {
        name: flowKind === 'node_flow' ? 'Nuevo NodoFlow' : 'Nuevo flow',
        definition,
        ...(flowKind ? { flow_kind: flowKind } : {}),
      })
      if (newFlow?.id) {
        setFlows(prev => [newFlow, ...prev])
        handleEdit(newFlow)
      }
    } finally {
      setCreating(false)
    }
  }

  async function handleEdit(flowSummary) {
    // Carga el detalle completo (con definition) antes de abrir el editor
    const full = await apiCall('GET', `/flows/bots/${botId}/${flowSummary.id}`, null)
    if (full?.id) setEditing(full)
  }

  async function handleToggleActive(flow) {
    await apiCall('PUT', `/flows/bots/${flow.bot_id}/${flow.id}`, { active: !flow.active })
    loadFlows()
  }

  async function handleDelete(flow) {
    if (!confirm(`¿Eliminar el flow "${flow.name}"? Esta acción no se puede deshacer.`)) return
    setDeleting(flow.id)
    await apiCall('DELETE', `/flows/bots/${flow.bot_id}/${flow.id}`, null)
    setFlows(prev => prev.filter(f => f.id !== flow.id))
    setDeleting(null)
  }

  // "Guardar como" en el editor crea un flow nuevo (inactivo) — lo abrimos directamente.
  function handleSavedAs(newFlow) {
    setFlows(prev => [newFlow, ...prev])
    setEditing(newFlow)
  }

  const regularFlows = flows.filter(f => f.flow_kind !== 'node_flow')
  const nodeFlows    = flows.filter(f => f.flow_kind === 'node_flow')
  const activeFlows = regularFlows.filter(f => f.active)
  const savedFlows  = regularFlows.filter(f => !f.active)

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <>
    {editing && (
      <div
        style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <div style={{
          background: 'var(--surface)',
          borderRadius: 16,
          width: '92vw',
          maxWidth: 1300,
          height: '88vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 24px 64px rgba(0,0,0,.35)',
        }}>
          <FlowEditor
            key={editing.id}
            flow={editing}
            connections={connections}
            apiCall={apiCall}
            typeMap={typeMap}
            onBack={() => { setEditing(null); loadFlows() }}
            onSaved={() => loadFlows()}
            onSavedAs={handleSavedAs}
            onGoToUIs={onGoToUIs}
          />
        </div>
      </div>
    )}
    {/* ── Lista ── */}
    <div style={{ padding: '16px 16px 8px' }}>
      {/* Header de la sección */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14 }}>
        <span style={{ fontSize: 13, color: 'var(--text-subtle)', flex: 1 }}>
          {flows.length} flow{flows.length !== 1 ? 's' : ''}
        </span>
        <button
          onClick={() => handleNew()}
          disabled={creating}
          style={{
            background: 'var(--success)',
            border: 'none',
            borderRadius: 6,
            color: '#fff',
            fontSize: 12,
            fontWeight: 600,
            padding: '5px 12px',
            cursor: creating ? 'default' : 'pointer',
          }}
        >
          {creating ? 'Creando...' : '+ Nuevo flow'}
        </button>
      </div>

      {/* Lista de flows */}
      {loading ? (
        <div className="empty" style={{ padding: '24px 0' }}>Cargando flows...</div>
      ) : flows.length === 0 ? (
        <div className="empty" style={{ padding: '24px 0' }}>Sin flows. Creá uno para empezar.</div>
      ) : (
        <>
          {/* Activos */}
          {activeFlows.length === 0 ? (
            <div className="empty" style={{ padding: '12px 0' }}>Sin flows activos.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {activeFlows.map(flow => (
                <FlowRow
                  key={flow.id}
                  flow={flow}
                  connections={connections}
                  onEdit={() => handleEdit(flow)}
                  onToggle={() => handleToggleActive(flow)}
                  onDelete={() => handleDelete(flow)}
                  isDeleting={deleting === flow.id}
                />
              ))}
            </div>
          )}

          {/* Guardados (inactivos) — colapsable */}
          {savedFlows.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <button
                onClick={() => setSavedExpanded(v => !v)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  width: '100%',
                  background: 'none',
                  border: 'none',
                  borderTop: '1px solid var(--surface-2)',
                  color: 'var(--text-subtle)',
                  fontSize: 12,
                  fontWeight: 600,
                  padding: '10px 2px 6px',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <span style={{ display: 'inline-block', transition: 'transform .15s', transform: savedExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>›</span>
                Guardados ({savedFlows.length})
              </button>

              {savedExpanded && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                  {savedFlows.map(flow => (
                    <FlowRow
                      key={flow.id}
                      flow={flow}
                      connections={connections}
                      onEdit={() => handleEdit(flow)}
                      onToggle={() => handleToggleActive(flow)}
                      onDelete={() => handleDelete(flow)}
                      isDeleting={deleting === flow.id}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* NodoFlows — flows reutilizables como nodo (flow_kind === 'node_flow') */}
      <div style={{ marginTop: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', borderTop: '1px solid var(--surface-2)', paddingTop: 10, marginBottom: 10 }}>
          <span style={{ fontSize: 13, color: 'var(--text-subtle)', flex: 1, fontWeight: 600 }}>
            NodoFlows ({nodeFlows.length})
          </span>
          <button
            onClick={() => handleNew('node_flow')}
            disabled={creating}
            style={{
              background: 'var(--tg)',
              border: 'none',
              borderRadius: 6,
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
              padding: '5px 12px',
              cursor: creating ? 'default' : 'pointer',
            }}
          >
            {creating ? 'Creando...' : '+ Nuevo NodoFlow'}
          </button>
        </div>

        {nodeFlows.length === 0 ? (
          <div className="empty" style={{ padding: '12px 0' }}>Sin NodoFlows. Creá uno o convertí una selección de nodos en un flow.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {nodeFlows.map(flow => (
              <FlowRow
                key={flow.id}
                flow={flow}
                connections={connections}
                onEdit={() => handleEdit(flow)}
                onToggle={() => handleToggleActive(flow)}
                onDelete={() => handleDelete(flow)}
                isDeleting={deleting === flow.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
    </>
  )
}

function FlowRow({ flow, connections, onEdit, onToggle, onDelete, isDeleting }) {
  const conn = connections?.find(c => c.id === flow.connection_id)
  const connLabel = conn
    ? `${CONNECTION_LABELS[conn.type] || conn.type} ${conn.number}`
    : flow.connection_id ? flow.connection_id : null

  return (
    <div
      className="flow-row"
      onClick={onEdit}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '9px 12px',
        background: 'var(--bg)',
        borderRadius: 8,
        border: '1px solid var(--surface-2)',
        cursor: 'pointer',
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-strong)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-2)'}
    >
      {/* Indicador activo */}
      <div style={{
        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
        background: flow.active ? 'var(--success)' : 'var(--text-subtle)',
      }} />

      {/* Nombre + metadatos */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {flow.name}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-subtle)', marginTop: 2 }}>
          {connLabel && <span style={{ marginRight: 8, color: 'var(--text-muted)' }}>{connLabel}</span>}
          {flow.contact_phone && <span style={{ marginRight: 8, color: 'var(--text-muted)' }}>{flow.contact_phone}</span>}
          <span>Editado {formatDate(flow.updated_at)}</span>
        </div>
      </div>

      <button
        onClick={e => { e.stopPropagation(); onToggle() }}
        title={flow.active ? 'Desactivar' : 'Activar'}
        style={{
          background: 'none',
          border: 'none',
          color: flow.active ? 'var(--success)' : 'var(--text-subtle)',
          cursor: 'pointer',
          fontSize: 15,
          padding: '2px 4px',
        }}
      >
        {flow.active ? '●' : '○'}
      </button>

      <button
        onClick={e => { e.stopPropagation(); onDelete() }}
        disabled={isDeleting}
        title="Eliminar flow"
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--danger-dim)',
          cursor: isDeleting ? 'default' : 'pointer',
          fontSize: 15,
          padding: '2px 4px',
        }}
      >
        ×
      </button>
    </div>
  )
}
