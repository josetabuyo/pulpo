/**
 * ConfigForm — formulario principal del panel de configuración de un nodo.
 *
 * Renderiza los campos del schema (dinámico, viene del backend) e inyecta
 * los datos extra que necesitan los tipos custom (conexiones, contactos,
 * cuentas Google). Suma las acciones específicas por tipo de nodo:
 * summarize (descarga/backup), sheets (caché), triggers (clonar filtro),
 * fetch FB (renovar sesión).
 */
import { useState, useEffect } from 'react'
import { useFlowStore } from '../../store/flowStore.js'
import { S } from './styles.js'
import { Field, isVisible } from './fields.jsx'
import SummarizeInfo from './SummarizeInfo.jsx'
import SheetCacheButton from './SheetCacheButton.jsx'

const TRIGGER_TYPES = new Set(['telegram_trigger', 'message_trigger', 'whatsapp_trigger'])

const FB_POLL_MS = 3_000        // intervalo de chequeo del login FB
const FB_MAX_WAIT_MS = 130_000  // corte del polling si el login nunca llega

export default function ConfigForm({ node, schema, empresaId, flowId, connections, apiCall, onGoToUIs }) {
  const updateNodeConfig  = useFlowStore(s => s.updateNodeConfig)
  const updateNodeLabel   = useFlowStore(s => s.updateNodeLabel)
  const deleteNode        = useFlowStore(s => s.deleteNode)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const { nodeType, config, label, color } = node.data
  const [contacts, setContacts]         = useState([])
  const [suggested, setSuggested]       = useState([])
  const [googleAccounts, setGoogleAccounts] = useState([])
  const [cloning, setCloning]           = useState(false)
  const [cloneMsg, setCloneMsg]     = useState('')
  const [fbRefreshing, setFbRefreshing] = useState(false)
  const [fbRefreshMsg, setFbRefreshMsg] = useState('')
  const [backupMsg, setBackupMsg]   = useState('')
  const [backingUp, setBackingUp]   = useState(false)
  const [showBackupConfirm, setShowBackupConfirm] = useState(false)

  const isFixed = nodeType === 'start' || nodeType === 'end'
  const isTrigger = TRIGGER_TYPES.has(nodeType)
  const isFbFetch = nodeType === 'fetch' && config.source === 'facebook'

  useEffect(() => {
    if (!empresaId || !apiCall) return
    Promise.all([
      apiCall('GET', `/bots/${empresaId}/contacts`, null).catch(() => []),
      apiCall('GET', `/bots/${empresaId}/contacts/suggested`, null).catch(() => []),
      apiCall('GET', `/empresas/${empresaId}/google-accounts`, null).catch(() => []),
    ]).then(([c, s, ga]) => {
      if (Array.isArray(c))  setContacts(c)
      if (Array.isArray(s))  setSuggested(s)
      if (Array.isArray(ga)) setGoogleAccounts(ga)
    })
  }, [empresaId])

  function handleChange(newConfig) { updateNodeConfig(node.id, newConfig) }
  function handleDelete() { if (!isFixed) deleteNode(node.id) }

  async function handleFbRefresh() {
    const pageId = config.fb_page_id || empresaId || 'luganense'
    setFbRefreshing(true)
    setFbRefreshMsg('Abriendo browser…')
    try {
      const res = await apiCall('POST', `/fb/refresh-session?page_id=${pageId}`, {})
      if (!res.ok) {
        setFbRefreshMsg('⚠ ' + (res.message || 'Error'))
        setTimeout(() => { setFbRefreshMsg(''); setFbRefreshing(false) }, 5000)
        return
      }
      setFbRefreshMsg('Esperando login en browser…')
      const poll = setInterval(async () => {
        try {
          const st = await apiCall('GET', `/fb/session-status?page_id=${pageId}`, null)
          if (st.state === 'ok') {
            setFbRefreshMsg('✓ Sesión renovada')
            clearInterval(poll)
            setTimeout(() => { setFbRefreshMsg(''); setFbRefreshing(false) }, 4000)
          } else if (st.state === 'error') {
            setFbRefreshMsg('⚠ ' + (st.message || 'Error'))
            clearInterval(poll)
            setTimeout(() => { setFbRefreshMsg(''); setFbRefreshing(false) }, 5000)
          }
        } catch { clearInterval(poll); setFbRefreshMsg(''); setFbRefreshing(false) }
      }, FB_POLL_MS)
      setTimeout(() => { clearInterval(poll); setFbRefreshMsg(''); setFbRefreshing(false) }, FB_MAX_WAIT_MS)
    } catch {
      setFbRefreshMsg('⚠ Error de red')
      setTimeout(() => { setFbRefreshMsg(''); setFbRefreshing(false) }, 4000)
    }
  }

  async function handleBackupAndClean() {
    setBackingUp(true)
    setBackupMsg('')
    setShowBackupConfirm(false)
    try {
      const result = await apiCall('POST', `/summarizer/${empresaId}/backup-and-clean`, {})
      setBackupMsg(`✓ Backup de ${result.backed_up} archivos. Los nuevos mensajes acumulan desde cero.`)
    } catch {
      setBackupMsg('Error al hacer backup')
    } finally {
      setBackingUp(false)
      setTimeout(() => setBackupMsg(''), 8000)
    }
  }

  async function handleDownloadSummaries() {
    try {
      const blob = await apiCall('GET_BLOB', `/summarizer/${empresaId}/download`, null)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `summaries_${empresaId}.zip`
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

  // Inyectar datos extra en los campos custom
  const visibleFields = (schema || []).filter(f => isVisible(f, config)).map(f => {
    if (f.type === 'connection_select')      return { ...f, _connections: connections || [] }
    if (f.type === 'contact_filter') {
      const connId = config.connection_id || ''
      const connObj = (connections || []).find(c => c.id === connId)
      return { ...f, _contacts: contacts, _suggested: suggested, _allow_mass: connObj?.allowMass ?? false }
    }
    if (f.type === 'google_account_select')  return { ...f, _google_accounts: googleAccounts }
    return f
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
        <input
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid transparent',
            color: '#e2e8f0',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'inherit',
            outline: 'none',
            padding: '1px 2px',
            cursor: 'text',
          }}
          value={label}
          onChange={e => updateNodeLabel(node.id, e.target.value)}
          onFocus={e => e.target.style.borderBottomColor = '#334155'}
          onBlur={e => e.target.style.borderBottomColor = 'transparent'}
          title="Editar nombre del nodo"
        />
        <span style={{
          fontSize: 10, color: '#94a3b8', fontFamily: 'monospace', flexShrink: 0,
          background: '#1e293b', border: '1px solid #334155', borderRadius: 4,
          padding: '2px 6px',
        }}>{nodeType}</span>
        <button
          onClick={() => setSelectedNodeId(null)}
          style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 2 }}
          title="Cerrar"
        >×</button>
      </div>

      <div style={{ borderTop: '1px solid #1e293b', paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 12, flex: 1, overflowY: 'auto' }}>

        {nodeType === 'summarize' && <SummarizeInfo empresaId={empresaId} apiCall={apiCall} onGoToUIs={onGoToUIs} />}

        {nodeType === 'summarize' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={S.label}>RESÚMENES</span>
            <button
              onClick={handleDownloadSummaries}
              style={{
                width: '100%', padding: '7px 12px',
                background: 'transparent', border: '1px solid #155e75',
                borderRadius: 6, color: '#22d3ee', fontSize: 12, cursor: 'pointer',
                fontWeight: 600,
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
                  background: 'transparent', border: '1px solid #7f1d1d',
                  borderRadius: 6, color: '#f87171', fontSize: 12, cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                {backingUp ? '⏳ Haciendo backup...' : '⚠ Backup y limpiar resúmenes'}
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ fontSize: 11, color: '#fbbf24', textAlign: 'center' }}>
                  Esto borra todos los .md actuales (quedan en .bak). ¿Confirmar?
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={handleBackupAndClean}
                    style={{
                      flex: 1, padding: '6px 8px',
                      background: '#7f1d1d', border: '1px solid #dc2626',
                      borderRadius: 6, color: '#fca5a5', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                    }}
                  >
                    Sí, limpiar
                  </button>
                  <button
                    onClick={() => setShowBackupConfirm(false)}
                    style={{
                      flex: 1, padding: '6px 8px',
                      background: 'transparent', border: '1px solid #334155',
                      borderRadius: 6, color: '#94a3b8', fontSize: 12, cursor: 'pointer',
                    }}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
            {backupMsg && (
              <div style={{ fontSize: 11, color: backupMsg.startsWith('✓') ? '#4ade80' : '#f87171', textAlign: 'center' }}>
                {backupMsg}
              </div>
            )}
          </div>
        )}

        {visibleFields.map(field => (
          <Field key={field.key} field={field} config={config} onChange={handleChange} />
        ))}

        {nodeType !== 'summarize' && visibleFields.length === 0 && (
          <div style={{ fontSize: 12, color: '#475569' }}>
            Este nodo no tiene configuración adicional.
          </div>
        )}

      </div>

      {['fetch_sheet', 'search_sheet', 'gsheet'].includes(nodeType) && (
        <SheetCacheButton apiCall={apiCall} />
      )}

      {isTrigger && config.connection_id && (
        <div style={{ paddingTop: 8, borderTop: '1px solid #1e293b', display: 'flex', flexDirection: 'column', gap: 6 }}>

          {config.contact_filter && (
            <>
              <button
                onClick={cloneFilterToDefault}
                disabled={cloning}
                style={{
                  width: '100%', padding: '5px 12px',
                  background: 'transparent', border: '1px solid #1e3a5f',
                  borderRadius: 6, color: '#60a5fa', fontSize: 11, cursor: 'pointer',
                }}
              >
                {cloning ? 'Copiando...' : '↓ Usar como default de la conexión'}
              </button>
              {cloneMsg && (
                <div style={{ fontSize: 10, color: '#60a5fa', textAlign: 'center' }}>{cloneMsg}</div>
              )}
            </>
          )}
        </div>
      )}

      {isFbFetch && (
        <div style={{ paddingTop: 8, borderTop: '1px solid #1e293b', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button
            onClick={handleFbRefresh}
            disabled={fbRefreshing}
            style={{
              width: '100%', padding: '7px 12px',
              background: 'transparent',
              border: '1px solid #1e3a5f',
              borderRadius: 6, color: '#60a5fa', fontSize: 12, cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {fbRefreshing ? '⏳ Esperando login…' : '↺ Renovar sesión FB'}
          </button>
          {fbRefreshMsg && (
            <div style={{ fontSize: 11, color: fbRefreshMsg.startsWith('✓') ? '#4ade80' : fbRefreshMsg.startsWith('⚠') ? '#f87171' : '#60a5fa', textAlign: 'center' }}>
              {fbRefreshMsg}
            </div>
          )}
        </div>
      )}

      {!isFixed && (
        <div style={{ paddingTop: 8 }}>
          <button
            onClick={handleDelete}
            style={{
              width: '100%',
              padding: '6px 12px',
              background: 'transparent',
              border: '1px solid #7f1d1d',
              borderRadius: 6,
              color: '#ef4444',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Eliminar nodo
          </button>
        </div>
      )}
    </div>
  )
}
