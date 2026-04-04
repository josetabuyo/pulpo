/**
 * FlowList — lista de flows de una empresa con acciones CRUD.
 *
 * Estados:
 *   - list: muestra la tabla de flows + botón "Nuevo flow"
 *   - editor: renderiza FlowEditor para el flow seleccionado
 */
import { useState, useEffect, useCallback } from 'react'
import FlowEditor from './FlowEditor.jsx'

const CONNECTION_LABELS = { whatsapp: 'WA', telegram: 'TG' }

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

export default function FlowList({ empresaId, apiCall, connections }) {
  const [flows,    setFlows]    = useState([])
  const [loading,  setLoading]  = useState(true)
  const [typeMap,  setTypeMap]  = useState({})
  const [editing,  setEditing]  = useState(null)   // flow completo (con definition)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState(null)

  const loadFlows = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiCall('GET', `/empresas/${empresaId}/flows`, null)
      if (Array.isArray(data)) setFlows(data)
    } finally {
      setLoading(false)
    }
  }, [empresaId, apiCall])

  // Cargar tipos de nodo una vez (necesarios para el editor)
  useEffect(() => {
    apiCall('GET', '/flow/node-types', null)
      .then(list => {
        if (Array.isArray(list)) {
          setTypeMap(Object.fromEntries(list.map(t => [t.id, t])))
        }
      })
      .catch(() => {})
  }, [apiCall])

  useEffect(() => { loadFlows() }, [loadFlows])

  async function handleNew() {
    setCreating(true)
    try {
      const definition = {
        nodes: [
          { id: '__start__', type: 'start', position: { x: 250, y: 50 },  config: {} },
          { id: '__end__',   type: 'end',   position: { x: 250, y: 250 }, config: {} },
        ],
        edges: [
          { id: 'e1', source: '__start__', target: '__end__', label: null },
        ],
        viewport: { x: 0, y: 0, zoom: 1 },
      }
      const newFlow = await apiCall('POST', `/empresas/${empresaId}/flows`, {
        name: 'Nuevo flow',
        definition,
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
    const full = await apiCall('GET', `/empresas/${empresaId}/flows/${flowSummary.id}`, null)
    if (full?.id) setEditing(full)
  }

  async function handleToggleActive(flow) {
    await apiCall('PUT', `/empresas/${flow.empresa_id}/flows/${flow.id}`, { active: !flow.active })
    loadFlows()
  }

  async function handleDelete(flow) {
    if (!confirm(`¿Eliminar el flow "${flow.name}"? Esta acción no se puede deshacer.`)) return
    setDeleting(flow.id)
    await apiCall('DELETE', `/empresas/${flow.empresa_id}/flows/${flow.id}`, null)
    setFlows(prev => prev.filter(f => f.id !== flow.id))
    setDeleting(null)
  }

  // ── Modo editor ──────────────────────────────────────────────────────────────

  if (editing) {
    return (
      <FlowEditor
        flow={editing}
        connections={connections}
        apiCall={apiCall}
        typeMap={typeMap}
        onBack={() => { setEditing(null); loadFlows() }}
        onSaved={() => loadFlows()}
      />
    )
  }

  // ── Modo lista ───────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: '16px 16px 8px' }}>
      {/* Header de la sección */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14 }}>
        <span style={{ fontSize: 13, color: '#94a3b8', flex: 1 }}>
          {flows.length} flow{flows.length !== 1 ? 's' : ''}
        </span>
        <button
          onClick={handleNew}
          disabled={creating}
          style={{
            background: '#16a34a',
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {flows.map(flow => (
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
  )
}

function FlowRow({ flow, connections, onEdit, onToggle, onDelete, isDeleting }) {
  // Encontrar label de la conexión si tiene una asignada
  const conn = connections?.find(c => c.id === flow.connection_id)
  const connLabel = conn
    ? `${CONNECTION_LABELS[conn.type] || conn.type} ${conn.number}`
    : flow.connection_id ? flow.connection_id : null

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '9px 12px',
      background: '#0f172a',
      borderRadius: 8,
      border: '1px solid #1e293b',
    }}>
      {/* Indicador activo */}
      <div style={{
        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
        background: flow.active ? '#16a34a' : '#475569',
      }} />

      {/* Nombre + metadatos */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: '#e2e8f0', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {flow.name}
        </div>
        <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>
          {connLabel && <span style={{ marginRight: 8, color: '#64748b' }}>{connLabel}</span>}
          {flow.contact_phone && <span style={{ marginRight: 8, color: '#64748b' }}>{flow.contact_phone}</span>}
          <span>Editado {formatDate(flow.updated_at)}</span>
        </div>
      </div>

      {/* Acciones */}
      <button
        onClick={onEdit}
        style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: 5,
          color: '#94a3b8',
          fontSize: 12,
          padding: '4px 10px',
          cursor: 'pointer',
        }}
      >
        Editar
      </button>

      <button
        onClick={onToggle}
        title={flow.active ? 'Desactivar' : 'Activar'}
        style={{
          background: 'none',
          border: 'none',
          color: flow.active ? '#16a34a' : '#475569',
          cursor: 'pointer',
          fontSize: 15,
          padding: '2px 4px',
        }}
      >
        {flow.active ? '●' : '○'}
      </button>

      <button
        onClick={onDelete}
        disabled={isDeleting}
        title="Eliminar flow"
        style={{
          background: 'none',
          border: 'none',
          color: '#7f1d1d',
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
