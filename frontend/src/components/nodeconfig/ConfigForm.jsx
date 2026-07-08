import { useState } from 'react'
import { useFlowStore } from '../../store/flowStore.js'
import { S } from './styles.js'
import SummarizeInfo from './SummarizeInfo.jsx'
import SheetCacheButton from './SheetCacheButton.jsx'
import FbCacheModal from './FbCacheModal.jsx'
import JsonNodeEditor from './JsonNodeEditor.jsx'

const TRIGGER_TYPES = new Set(['telegram_trigger', 'message_trigger', 'whatsapp_trigger', 'api_trigger'])

const FB_POLL_MS = 3_000
const FB_MAX_WAIT_MS = 130_000

export default function ConfigForm({ node, schema, botId, flowId, connections, apiCall, onGoToUIs }) {
  const updateNodeConfig = useFlowStore(s => s.updateNodeConfig)
  const { nodeType, config } = node.data

  const [cloning, setCloning]           = useState(false)
  const [cloneMsg, setCloneMsg]         = useState('')
  const [fbRefreshing, setFbRefreshing] = useState(false)
  const [fbRefreshMsg, setFbRefreshMsg] = useState('')
  const [showFbCache, setShowFbCache]   = useState(false)
  const [backupMsg, setBackupMsg]       = useState('')
  const [backingUp, setBackingUp]       = useState(false)
  const [showBackupConfirm, setShowBackupConfirm] = useState(false)

  const isTrigger = TRIGGER_TYPES.has(nodeType)
  const isFbFetch = nodeType === 'fetch_fb'

  function handleChange(newConfig) { updateNodeConfig(node.id, newConfig) }

  async function handleFbRefresh() {
    const pageId = config.fb_page_id || botId || 'luganense'
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
          <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.5 }}>
            Enviá un <code style={{ color: '#60a5fa' }}>POST</code> a esta URL para disparar el flow:
          </div>
          <div style={{
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: 6,
            padding: '8px 10px',
            fontFamily: 'monospace',
            fontSize: 10,
            color: '#a78bfa',
            wordBreak: 'break-all',
            cursor: 'pointer',
            userSelect: 'all',
          }}
            title="Clic para seleccionar"
          >
            {window.location.origin}/api/flows/{flowId}/trigger/{node.id}
          </div>
          <div style={{ fontSize: 10, color: '#475569' }}>
            Body JSON opcional: <code style={{ color: '#64748b' }}>{`{"message":"texto","contact_phone":"id"}`}</code>
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
              background: 'transparent', border: '1px solid #155e75',
              borderRadius: 6, color: '#22d3ee', fontSize: 12, cursor: 'pointer', fontWeight: 600,
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
                borderRadius: 6, color: '#f87171', fontSize: 12, cursor: 'pointer', fontWeight: 600,
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

      {/* JSON config editor */}
      <JsonNodeEditor
        config={config}
        schema={schema}
        onChange={handleChange}
      />

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
              background: 'transparent', border: '1px solid #1e3a5f',
              borderRadius: 6, color: '#60a5fa', fontSize: 11, cursor: 'pointer',
            }}
          >
            {cloning ? 'Copiando...' : '↓ Usar como default de la conexión'}
          </button>
          {cloneMsg && (
            <div style={{ fontSize: 10, color: '#60a5fa', textAlign: 'center' }}>{cloneMsg}</div>
          )}
        </div>
      )}

      {/* FB fetch */}
      {isFbFetch && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button
            onClick={handleFbRefresh}
            disabled={fbRefreshing}
            style={{
              width: '100%', padding: '7px 12px',
              background: 'transparent', border: '1px solid #1e3a5f',
              borderRadius: 6, color: '#60a5fa', fontSize: 12, cursor: 'pointer', fontWeight: 600,
            }}
          >
            {fbRefreshing ? '⏳ Esperando login…' : '↺ Renovar sesión FB'}
          </button>
          {fbRefreshMsg && (
            <div style={{
              fontSize: 11, textAlign: 'center',
              color: fbRefreshMsg.startsWith('✓') ? '#4ade80' : fbRefreshMsg.startsWith('⚠') ? '#f87171' : '#60a5fa',
            }}>
              {fbRefreshMsg}
            </div>
          )}
          <button
            onClick={() => setShowFbCache(true)}
            style={{
              width: '100%', padding: '7px 12px',
              background: 'transparent', border: '1px solid #1e293b',
              borderRadius: 6, color: '#64748b', fontSize: 12, cursor: 'pointer',
            }}
          >
            Ver cache FB
          </button>
        </div>
      )}

      {showFbCache && (
        <FbCacheModal
          pageId={config.fb_page_id || 'luganense'}
          apiCall={apiCall}
          onClose={() => setShowFbCache(false)}
        />
      )}
    </div>
  )
}
