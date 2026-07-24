/**
 * TriggersTab — reemplaza la vieja tab "Conexiones" (2026-07-23).
 *
 * Lista, de TODOS los flows de la bot, únicamente los nodos que son
 * triggers reales (telegram_trigger, whatsapp_trigger, trigger_chat) — no
 * hay más una capa de "conexión" administrada aparte: cada trigger es dueño
 * de su propia config (incluida la conexión que usa), editable desde el
 * propio nodo en el editor de flow ("Configurar" abre ese nodo ahí mismo,
 * no un formulario paralelo).
 *
 * Acciones por fila:
 *   - Pausar/Reanudar: toggle de config.paused, PATCH liviano sin reabrir
 *     el editor.
 *   - Configurar: delega al padre (BotCard → tab Flow con el nodo
 *     seleccionado).
 *   - Simular: solo triggers de mensaje, abre SimulateModal.
 */
import { useState, useEffect, useCallback } from 'react'
import SimulateModal from './SimulateModal.jsx'

const MESSAGE_TRIGGER_TYPES = new Set(['telegram_trigger', 'whatsapp_trigger', 'trigger_chat'])

function TriggerChip({ typeMeta, nodeType }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <span style={{
        width: 8, height: 8, borderRadius: 2, flexShrink: 0,
        background: typeMeta?.color || 'var(--text-subtle)',
      }} />
      <span style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-subtle)' }}>
        {typeMeta?.label || nodeType}
      </span>
    </span>
  )
}

export default function TriggersTab({ botId, apiCall, onConfigureNode }) {
  const [typeMap, setTypeMap] = useState({})
  const [triggers, setTriggers] = useState([])
  const [loading, setLoading] = useState(true)
  const [pausingId, setPausingId] = useState(null)
  const [simulating, setSimulating] = useState(null) // { flowId, nodeId, label }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const list = await apiCall('GET', `/bots/${botId}/triggers`, null)
      if (Array.isArray(list)) setTriggers(list)
    } finally {
      setLoading(false)
    }
  }, [botId, apiCall])

  useEffect(() => {
    apiCall('GET', '/flows/node-types', null)
      .then(list => { if (Array.isArray(list)) setTypeMap(Object.fromEntries(list.map(t => [t.id, t]))) })
      .catch(() => {})
  }, [apiCall])

  useEffect(() => { load() }, [load])

  async function togglePause(trigger) {
    setPausingId(trigger.nodeId)
    try {
      const nextConfig = { ...trigger.config, paused: !trigger.config?.paused }
      const res = await apiCall(
        'PATCH',
        `/flows/bots/${botId}/${trigger.flowId}/nodes/${trigger.nodeId}/config`,
        { config: nextConfig },
      ).catch(() => null)
      if (res?.config) {
        setTriggers(prev => prev.map(t => (t.nodeId === trigger.nodeId && t.flowId === trigger.flowId)
          ? { ...t, config: res.config }
          : t))
      }
    } finally {
      setPausingId(null)
    }
  }

  // Agrupado por flow — más legible que una lista plana cuando hay varios.
  const byFlow = {}
  for (const t of triggers) {
    if (!byFlow[t.flowId]) byFlow[t.flowId] = { flowName: t.flowName, items: [] }
    byFlow[t.flowId].items.push(t)
  }

  if (loading) return <div className="empty" style={{ padding: '24px 0' }}>Cargando triggers...</div>

  if (triggers.length === 0) {
    return (
      <div className="empty" style={{ padding: '24px 16px' }}>
        Sin triggers configurados. Agregá un nodo trigger (Telegram, WhatsApp o Chat)
        desde el editor de Flow para que aparezca acá.
      </div>
    )
  }

  return (
    <div style={{ padding: '12px 16px' }}>
      {Object.entries(byFlow).map(([flowId, group]) => (
        <div key={flowId} style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
            {group.flowName}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {group.items.map(trigger => {
              const paused = Boolean(trigger.config?.paused)
              const isMessageTrigger = MESSAGE_TRIGGER_TYPES.has(trigger.nodeType)
              return (
                <div
                  key={trigger.nodeId}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px',
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                  }}
                >
                  <TriggerChip typeMeta={typeMap[trigger.nodeType]} nodeType={trigger.nodeType} />
                  <span style={{
                    fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 10,
                    background: paused ? 'var(--warning-dim, rgba(217,119,6,.12))' : 'var(--success-dim)',
                    color: paused ? 'var(--warning)' : 'var(--success)',
                  }}>
                    {paused ? 'Pausado' : 'Activo'}
                  </span>
                  <span style={{ flex: 1 }} />
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => togglePause(trigger)}
                    disabled={pausingId === trigger.nodeId}
                    title={paused ? 'Reanudar este trigger' : 'Pausar este trigger'}
                  >
                    {pausingId === trigger.nodeId ? '...' : paused ? '▶ Reanudar' : '⏸ Pausar'}
                  </button>
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => onConfigureNode?.(trigger.flowId, trigger.nodeId)}
                  >
                    Configurar
                  </button>
                  {isMessageTrigger && (
                    <button
                      className="btn-ghost btn-sm"
                      onClick={() => setSimulating({ flowId: trigger.flowId, nodeId: trigger.nodeId, label: typeMap[trigger.nodeType]?.label || trigger.nodeType })}
                    >
                      Simular
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {simulating && (
        <SimulateModal
          apiCall={apiCall}
          flowId={simulating.flowId}
          nodeId={simulating.nodeId}
          label={simulating.label}
          onClose={() => setSimulating(null)}
        />
      )}
    </div>
  )
}
