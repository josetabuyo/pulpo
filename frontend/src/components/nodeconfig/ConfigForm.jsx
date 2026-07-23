import { useState, useEffect } from 'react'
import { useFlowStore } from '../../store/flowStore.js'
import { S } from './styles.js'
import SummarizeInfo from './SummarizeInfo.jsx'
import SheetCacheButton from './SheetCacheButton.jsx'
import JsonNodeEditor from './JsonNodeEditor.jsx'

const TRIGGER_TYPES = new Set(['telegram_trigger', 'message_trigger', 'whatsapp_trigger', 'api_trigger'])

export default function ConfigForm({ node, schema, botId, flowId, apiCall, onGoToUIs }) {
  const updateNodeConfig = useFlowStore(s => s.updateNodeConfig)
  const { nodeType, config } = node.data

  const [cloning, setCloning]           = useState(false)
  const [cloneMsg, setCloneMsg]         = useState('')
  const [backupMsg, setBackupMsg]       = useState('')
  const [backingUp, setBackingUp]       = useState(false)
  const [showBackupConfirm, setShowBackupConfirm] = useState(false)
  const [nodeFlows, setNodeFlows]       = useState([])

  const isTrigger = TRIGGER_TYPES.has(nodeType)

  function handleChange(newConfig) { updateNodeConfig(node.id, newConfig) }

  // NodoFlow: cargar la lista de flows reutilizables (flow_kind === 'node_flow')
  // del bot, para poblar el selector dinámicamente (ver SPEC_NODOFLOW.md).
  useEffect(() => {
    if (nodeType !== 'nodo_flow' || !botId) return
    let cancelled = false
    apiCall('GET', `/flows/bots/${botId}/node-flows`, null)
      .then(list => { if (!cancelled && Array.isArray(list)) setNodeFlows(list) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [nodeType, botId, apiCall])

  async function handleBackupAndClean() {
    setBackingUp(true)
    setBackupMsg('')
    setShowBackupConfirm(false)
    try {
      const result = await apiCall('POST', `/summarizer/${botId}/backup-and-clean`, {})
      setBackupMsg(`✓ Backup de ${result.backed_up} archivos.`)
    } catch {
      setBackupMsg('Error al hacer backup')
    } finally {
      setBackingUp(false)
      setTimeout(() => setBackupMsg(''), 8000)
    }
  }

  async function handleDownloadSummaries() {
    try {
      const blob = await apiCall('GET_BLOB', `/summarizer/${botId}/download`, null)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `summaries_${botId}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.warn('[ConfigForm] descarga de resúmenes falló', e)
    }
  }

  async function cloneFilterToDefault() {
    const connectionId = config.connection_id
    const contactFilter = config.contact_filter
    if (!connectionId || !contactFilter) {
      setCloneMsg('Falta conexión o filtro en el nodo')
      setTimeout(() => setCloneMsg(''), 3000)
      return
    }
    setCloning(true)
    await apiCall('PUT', `/connections/${connectionId}/filter-config`, contactFilter).catch(() => null)
    setCloning(false)
    setCloneMsg('✓ Filtro copiado como default de la conexión')
    setTimeout(() => setCloneMsg(''), 4000)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, flex: 1, minHeight: 0 }}>

      {/* API trigger endpoint info */}
      {nodeType === 'api_trigger' && flowId && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={S.label}>ENDPOINT</span>
          <div style={{ fontSize: 11, color: 'var(--text-subtle)', lineHeight: 1.5 }}>
            Enviá un <code style={{ color: 'var(--tg)' }}>POST</code> a esta URL para disparar el flow:
          </div>
          <div style={{
            background: 'var(--bg)',
            border: '1px solid var(--border-strong)',
            borderRadius: 6,
            padding: '8px 10px',
            fontFamily: 'monospace',
            fontSize: 10,
            color: 'var(--brand-light)',
            wordBreak: 'break-all',
            cursor: 'pointer',
            userSelect: 'all',
          }}
            title="Clic para seleccionar"
          >
            {window.location.origin}/api/flows/{flowId}/trigger/{node.id}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-subtle)' }}>
            Body JSON opcional: <code style={{ color: 'var(--text-muted)' }}>{`{"message":"texto","contact_phone":"id"}`}</code>
          </div>
        </div>
      )}

      {/* Summarize */}
      {nodeType === 'summarize' && <SummarizeInfo botId={botId} apiCall={apiCall} onGoToUIs={onGoToUIs} />}
      {nodeType === 'summarize' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={S.label}>RESÚMENES</span>
          <button
            onClick={handleDownloadSummaries}
            style={{
              width: '100%', padding: '7px 12px',
              background: 'transparent', border: '1px solid var(--tg)',
              borderRadius: 6, color: 'var(--tg)', fontSize: 12, cursor: 'pointer', fontWeight: 600,
            }}
          >
            ↓ Descargar resúmenes (.zip)
          </button>
          {!showBackupConfirm ? (
            <button
              onClick={() => setShowBackupConfirm(true)}
              disabled={backingUp}
              style={{
                width: '100%', padding: '7px 12px',
                background: 'transparent', border: '1px solid var(--danger-dim)',
                borderRadius: 6, color: 'var(--danger)', fontSize: 12, cursor: 'pointer', fontWeight: 600,
              }}
            >
              {backingUp ? '⏳ Haciendo backup...' : '⚠ Backup y limpiar resúmenes'}
            </button>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ fontSize: 11, color: 'var(--warning)', textAlign: 'center' }}>
                Esto borra todos los .md actuales (quedan en .bak). ¿Confirmar?
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  onClick={handleBackupAndClean}
                  style={{
                    flex: 1, padding: '6px 8px',
                    background: 'var(--danger-dim)', border: '1px solid var(--danger)',
                    borderRadius: 6, color: 'var(--danger)', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                  }}
                >
                  Sí, limpiar
                </button>
                <button
                  onClick={() => setShowBackupConfirm(false)}
                  style={{
                    flex: 1, padding: '6px 8px',
                    background: 'transparent', border: '1px solid var(--border-strong)',
                    borderRadius: 6, color: 'var(--text-subtle)', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}
          {backupMsg && (
            <div style={{ fontSize: 11, color: backupMsg.startsWith('✓') ? 'var(--success)' : 'var(--danger)', textAlign: 'center' }}>
              {backupMsg}
            </div>
          )}
        </div>
      )}

      {/* NodoFlow: selector de sub-flow — la config en sí (params/output/routes)
          se edita como JSON crudo abajo, igual que cualquier otro node type
          (ver feedback del usuario: los inputs sueltos por param rompían el
          criterio de edición uniforme). Al elegir un flow, auto-completamos
          config.routes con las salidas reales del sub-flow (compute_exit_routes,
          ya vienen resueltas en la respuesta de /node-flows) — única escritura
          automática que hace esta sección. El color NO se copia acá: se
          resuelve en vivo contra la variable "color" del sub-flow elegido
          (ver flowStore.js::baseTypeColor/setNodeFlowColors) para que cambiar
          el color del sub-flow se refleje en todos los nodos que lo usan sin
          tener que reabrirlos uno por uno. */}
      {nodeType === 'nodo_flow' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={S.label}>SUB-FLOW</span>
          <select
            value={config.flow_id || ''}
            onChange={e => {
              const flow_id = e.target.value
              const selected = nodeFlows.find(f => f.id === flow_id)
              handleChange({ ...config, flow_id, routes: selected?.routes || [] })
            }}
            style={{
              width: '100%', padding: '6px 8px',
              background: 'var(--bg)', border: '1px solid var(--border-strong)',
              borderRadius: 6, color: 'var(--text)', fontSize: 12,
            }}
          >
            <option value="">(elegir un flow)</option>
            {nodeFlows.map(f => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
        </div>
      )}

      {/* JSON config editor */}
      <JsonNodeEditor
        config={config}
        schema={schema}
        onChange={handleChange}
      />

      {/* NodoFlow: referencia de solo lectura del sub-flow elegido — documenta
          qué claves agregar sueltas en el JSON de arriba (junto a flow_id/
          output/routes, sin anidar), no es un formulario editable. */}
      {nodeType === 'nodo_flow' && (() => {
        const selectedFlow = nodeFlows.find(f => f.id === config.flow_id)
        if (!selectedFlow) return null
        const inputs = selectedFlow.inputs || []
        const routes = selectedFlow.routes || []
        return (
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 8,
            background: 'var(--bg)', border: '1px solid var(--surface-2)',
            borderRadius: 6, padding: '8px 10px',
          }}>
            <span style={{ fontSize: 9, color: 'var(--border-strong)', fontWeight: 700, letterSpacing: '0.12em' }}>
              REFERENCIA DEL SUB-FLOW — PARÁMETROS Y SALIDAS DISPONIBLES
            </span>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>parámetros (claves sueltas en el JSON)</span>
              {inputs.length > 0 ? inputs.map(input => (
                <div key={input.key} style={{ fontSize: 11, color: 'var(--text-subtle)', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <code style={{ color: 'var(--tg)' }}>{input.key}</code>
                  {input.label && <span>{input.label}</span>}
                  <span style={{ color: 'var(--text-subtle)' }}>
                    ({input.type || 'text'}{input.default != null && input.default !== '' ? `, default: ${input.default}` : ''})
                  </span>
                </div>
              )) : (
                <span style={{ fontSize: 11, color: 'var(--text-subtle)' }}>Este sub-flow no declara parámetros.</span>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>routes (salidas)</span>
              {routes.length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {routes.map(r => (
                    <span key={r} style={{
                      fontSize: 10, padding: '2px 6px', borderRadius: 10,
                      background: 'var(--surface-2)', color: 'var(--success)', fontFamily: 'monospace',
                    }}>
                      {r}
                    </span>
                  ))}
                </div>
              ) : (
                <span style={{ fontSize: 11, color: 'var(--text-subtle)' }}>
                  Este sub-flow no expone salidas nombradas (sale sin ruta etiquetada).
                </span>
              )}
            </div>
          </div>
        )
      })()}

      {/* Sheet cache */}
      {['fetch_sheet', 'search_sheet', 'gsheet'].includes(nodeType) && (
        <SheetCacheButton apiCall={apiCall} />
      )}

      {/* Trigger: clone filter */}
      {isTrigger && config.connection_id && config.contact_filter && (
        <div style={{ paddingTop: 4, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <button
            onClick={cloneFilterToDefault}
            disabled={cloning}
            style={{
              width: '100%', padding: '5px 12px',
              background: 'transparent', border: '1px solid var(--tg)',
              borderRadius: 6, color: 'var(--tg)', fontSize: 11, cursor: 'pointer',
            }}
          >
            {cloning ? 'Copiando...' : '↓ Usar como default de la conexión'}
          </button>
          {cloneMsg && (
            <div style={{ fontSize: 10, color: 'var(--tg)', textAlign: 'center' }}>{cloneMsg}</div>
          )}
        </div>
      )}

    </div>
  )
}
