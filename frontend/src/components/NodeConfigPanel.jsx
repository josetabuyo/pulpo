/**
 * NodeConfigPanel — panel lateral derecho para configurar el nodo seleccionado.
 *
 * Totalmente dinámico: el schema de cada nodo viene del backend via
 * GET /api/flow/node-types → typeMap[nodeType].schema
 *
 * Agregar un nodo nuevo = solo Python. El panel aparece solo.
 *
 * Tipos de campo soportados: string, textarea, select, float, bool, list.
 * Campos condicionales: show_if: { campo: valor } — se ocultan si no se cumple.
 */
import { useState, useEffect } from 'react'
import { useFlowStore } from '../store/flowStore.js'
import ContactFilterEditor, { DEFAULT_FILTER } from './ContactFilterEditor.jsx'

// ─── Estilos base ─────────────────────────────────────────────────────────────

const S = {
  label: {
    fontSize: 10,
    color: '#64748b',
    fontWeight: 700,
    letterSpacing: '0.06em',
    marginBottom: 4,
    display: 'block',
  },
  hint: {
    fontSize: 10,
    color: '#475569',
    marginTop: 3,
  },
  input: {
    width: '100%',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 12,
    padding: '6px 9px',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    outline: 'none',
  },
  textarea: {
    width: '100%',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 12,
    padding: '6px 9px',
    resize: 'vertical',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    outline: 'none',
    minHeight: 80,
  },
  select: {
    width: '100%',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 12,
    padding: '6px 9px',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    outline: 'none',
    cursor: 'pointer',
  },
  checkRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  fieldWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
}

// ─── Visibilidad condicional ───────────────────────────────────────────────────

/**
 * show_if viene del backend como { campo: valor }.
 * El campo es visible si TODOS los pares se cumplen en config.
 */
function isVisible(field, config) {
  if (!field.show_if) return true
  return Object.entries(field.show_if).every(([k, v]) => config[k] === v)
}

// ─── Campo JSON editable ───────────────────────────────────────────────────────

function JsonField({ field, value, set, labelEl }) {
  const { hint } = field
  const [raw, setRaw]     = useState(JSON.stringify(value, null, 2))
  const [error, setError] = useState(null)

  // Sync externo → local (cuando el nodo cambia)
  useEffect(() => {
    setRaw(JSON.stringify(value, null, 2))
    setError(null)
  }, [JSON.stringify(value)])

  function handleChange(text) {
    setRaw(text)
    try {
      const parsed = JSON.parse(text)
      setError(null)
      set(parsed)
    } catch {
      setError('JSON inválido')
    }
  }

  return (
    <div style={S.fieldWrap}>
      {labelEl}
      <textarea
        style={{
          ...S.textarea,
          minHeight: 160,
          fontFamily: 'monospace',
          fontSize: 11,
          border: error ? '1px solid #ef4444' : S.textarea.border,
        }}
        value={raw}
        onChange={e => handleChange(e.target.value)}
        spellCheck={false}
      />
      {error && <span style={{ ...S.hint, color: '#ef4444' }}>{error}</span>}
      {!error && hint && <span style={S.hint}>{hint}</span>}
    </div>
  )
}

// ─── ContactFilterPopup ───────────────────────────────────────────────────────
// Muestra un resumen del filtro + botón que abre un popup/modal con el editor.

function ContactFilterPopup({ label, value, onChange, contacts, suggested }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)

  // Sincronizar draft cuando cambia el valor externo (ej: clonar a default)
  useEffect(() => { setDraft(value) }, [value])

  function handleOpen() { setDraft(value); setOpen(true) }
  function handleSave() { onChange(draft); setOpen(false) }
  function handleClose() { setOpen(false) }

  const cf = value || {}
  const excludedCount = (cf.excluded || []).length
  const includedCount = (cf.included || []).length

  const summaryParts = []
  if (cf.include_all_known) summaryParts.push('todos conocidos')
  if (cf.include_unknown) summaryParts.push('desconocidos')
  if (includedCount) summaryParts.push(`${includedCount} incluidos`)
  if (excludedCount) summaryParts.push(`${excludedCount} excluidos`)

  return (
    <>
      <div style={S.fieldWrap}>
        <span style={S.label}>{label}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, color: summaryParts.length ? '#94a3b8' : '#ef4444', flex: 1 }}>
            {summaryParts.length ? summaryParts.join(' · ') : '⚠ Sin filtro activo'}
          </span>
          <button
            onClick={handleOpen}
            style={{
              fontSize: 10, padding: '3px 8px', borderRadius: 4, cursor: 'pointer',
              background: 'transparent', border: '1px solid #334155', color: '#94a3b8',
              flexShrink: 0,
            }}
          >
            Editar filtro
          </button>
        </div>
      </div>

      {open && (
        <div
          onClick={e => e.target === e.currentTarget && handleClose()}
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <div style={{
            background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10,
            width: 360, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
            boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
          }}>
            <div style={{ padding: '12px 16px 8px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center' }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', flex: 1 }}>Filtro de contactos</span>
              <button onClick={handleClose} style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 2 }}>×</button>
            </div>
            <div style={{ padding: '10px 16px', overflowY: 'auto', flex: 1 }}>
              <ContactFilterEditor
                value={draft}
                onChange={setDraft}
                contacts={contacts}
                suggested={suggested}
              />
            </div>
            <div style={{ padding: '8px 16px 12px', borderTop: '1px solid #1e293b', display: 'flex', gap: 8 }}>
              <button
                onClick={handleSave}
                style={{
                  flex: 1, padding: '6px 12px', borderRadius: 6, cursor: 'pointer',
                  background: '#6b21a8', border: 'none', color: '#fff', fontSize: 12, fontWeight: 600,
                }}
              >
                Guardar
              </button>
              <button
                onClick={handleClose}
                style={{
                  padding: '6px 12px', borderRadius: 6, cursor: 'pointer',
                  background: 'transparent', border: '1px solid #334155', color: '#94a3b8', fontSize: 12,
                }}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Render de un campo ───────────────────────────────────────────────────────

function Field({ field, config, onChange }) {
  const { key, label, type, hint, rows = 4, options = [], required } = field
  const value = config[key] ?? field.default ?? (type === 'bool' ? false : type === 'list' ? [] : type === 'json' ? [] : '')

  function set(val) { onChange({ ...config, [key]: val }) }

  const labelEl = (
    <label style={S.label}>
      {label.toUpperCase()}{required && <span style={{ color: '#ef4444' }}> *</span>}
    </label>
  )

  if (type === 'json') return (
    <JsonField field={field} value={value} set={set} labelEl={labelEl} />
  )

  if (type === 'textarea') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <textarea
        style={S.textarea}
        rows={rows}
        value={value}
        onChange={e => set(e.target.value)}
        placeholder={hint || ''}
      />
    </div>
  )

  if (type === 'select') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <select style={S.select} value={value} onChange={e => set(e.target.value)}>
        {options.map(o => {
          const val = typeof o === 'object' ? o.value : o
          const lbl = typeof o === 'object' ? o.label : o
          return <option key={val} value={val}>{lbl}</option>
        })}
      </select>
    </div>
  )

  if (type === 'float') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="number"
        step="0.1"
        value={value}
        onChange={e => set(parseFloat(e.target.value) || 0)}
      />
    </div>
  )

  if (type === 'number') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="number"
        step="1"
        min="0"
        value={value}
        onChange={e => set(parseFloat(e.target.value) || 0)}
      />
      {hint && <span style={S.hint}>{hint}</span>}
    </div>
  )

  if (type === 'bool') return (
    <div style={S.fieldWrap}>
      <div style={S.checkRow}>
        <input
          id={key}
          type="checkbox"
          checked={!!value}
          onChange={e => set(e.target.checked)}
          style={{ accentColor: '#6b21a8', cursor: 'pointer' }}
        />
        <label htmlFor={key} style={{ ...S.label, margin: 0, cursor: 'pointer', fontSize: 12, color: '#cbd5e1', fontWeight: 400, letterSpacing: 0 }}>
          {label}
        </label>
      </div>
    </div>
  )

  if (type === 'list') {
    const csv = Array.isArray(value) ? value.join(', ') : value
    return (
      <div style={S.fieldWrap}>
        {labelEl}
        <input
          style={S.input}
          type="text"
          value={csv}
          onChange={e => set(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
          placeholder={hint || 'val1, val2, val3'}
        />
        {hint && <span style={S.hint}>{hint}</span>}
      </div>
    )
  }

  // Tipos custom — se pasan desde ConfigForm que tiene acceso a connections/contacts
  // Se usa un patrón de render-prop: Field espera extra={} con los datos necesarios
  if (type === 'connection_select') {
    const connections = field._connections || []
    return (
      <div style={S.fieldWrap}>
        {labelEl}
        <select style={S.select} value={value} onChange={e => set(e.target.value)}>
          <option value="">— Sin conexión —</option>
          {connections.map(c => (
            <option key={c.id} value={c.id}>{c.number || c.id}</option>
          ))}
        </select>
      </div>
    )
  }

  if (type === 'contact_filter') {
    return (
      <div style={S.fieldWrap}>
        {labelEl}
        <ContactFilterEditor
          value={value}
          onChange={cf => set(cf)}
          contacts={field._contacts || []}
          suggested={field._suggested || []}
        />
      </div>
    )
  }

  if (type === 'google_account_select') {
    const accounts = field._google_accounts || []
    const selected = accounts.find(a => a.id === value) || accounts[0]
    const [copied, setCopied] = useState(false)
    function copy() {
      if (!selected) return
      navigator.clipboard.writeText(selected.email)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={S.fieldWrap}>
          {labelEl}
          {accounts.length === 0 ? (
            <span style={{ fontSize: 11, color: '#ef4444' }}>
              No hay cuentas Google configuradas (falta GOOGLE_SERVICE_ACCOUNT_JSON en .env)
            </span>
          ) : (
            <select
              style={S.select}
              value={value}
              onChange={e => set(e.target.value)}
            >
              {accounts.map(a => (
                <option key={a.id} value={a.id}>{a.label} — {a.email}</option>
              ))}
            </select>
          )}
        </div>
        {selected && (
          <div style={{
            background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6,
            padding: '7px 10px', display: 'flex', flexDirection: 'column', gap: 4,
          }}>
            <span style={{ fontSize: 10, color: '#60a5fa', fontWeight: 700, letterSpacing: '0.06em' }}>
              COMPARTIR PLANILLA CON PULPO
            </span>
            <span style={{ fontSize: 10, color: '#64748b', lineHeight: 1.5 }}>
              Para que este nodo pueda acceder a tu Google Sheet, compartila con este email:
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
                {selected.email}
              </span>
              <button
                onClick={copy}
                style={{
                  fontSize: 10, padding: '2px 7px', borderRadius: 4, cursor: 'pointer',
                  background: copied ? '#166534' : 'transparent',
                  border: `1px solid ${copied ? '#16a34a' : '#334155'}`,
                  color: copied ? '#4ade80' : '#64748b',
                  flexShrink: 0, transition: 'all 0.2s',
                }}
              >
                {copied ? 'Copiado' : 'Copiar'}
              </button>
            </div>
          </div>
        )}
      </div>
    )
  }

  if (type === 'info') {
    const [copied, setCopied] = useState(false)
    function copy() {
      navigator.clipboard.writeText(hint || label)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
    return (
      <div style={{
        background: '#0f172a', border: '1px solid #1e3a5f', borderRadius: 6,
        padding: '7px 10px', display: 'flex', flexDirection: 'column', gap: 4,
      }}>
        <span style={{ fontSize: 10, color: '#60a5fa', fontWeight: 700, letterSpacing: '0.06em' }}>
          {label.toUpperCase()}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
            {hint || label}
          </span>
          <button
            onClick={copy}
            style={{
              fontSize: 10, padding: '2px 7px', borderRadius: 4, cursor: 'pointer',
              background: copied ? '#166534' : 'transparent',
              border: `1px solid ${copied ? '#16a34a' : '#334155'}`,
              color: copied ? '#4ade80' : '#64748b',
              flexShrink: 0, transition: 'all 0.2s',
            }}
          >
            {copied ? 'Copiado' : 'Copiar'}
          </button>
        </div>
      </div>
    )
  }

  // string (default)
  return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="text"
        value={value}
        onChange={e => set(e.target.value)}
        placeholder={hint || ''}
      />
      {hint && <span style={S.hint}>{hint}</span>}
    </div>
  )
}

// ─── Info especial: Sumarizador ────────────────────────────────────────────────

function SheetCacheButton({ apiCall }) {
  const [status, setStatus] = useState('')
  async function handleClear() {
    setStatus('Limpiando...')
    try {
      const res = await apiCall('POST', '/flow/clear-sheet-cache', null)
      setStatus(`✓ Caché limpiado (${res.cleared} entradas)`)
    } catch {
      setStatus('Error al limpiar')
    }
    setTimeout(() => setStatus(''), 3000)
  }
  return (
    <div style={{ paddingTop: 8, borderTop: '1px solid #1e293b' }}>
      <button
        onClick={handleClear}
        style={{
          width: '100%', padding: '7px 12px',
          background: 'transparent', border: '1px solid #0e7490',
          borderRadius: 6, color: '#22d3ee', fontSize: 12,
          cursor: 'pointer', fontWeight: 600,
        }}
      >
        🗑 Limpiar caché de hoja
      </button>
      {status && <div style={{ fontSize: 11, color: '#22d3ee', textAlign: 'center', marginTop: 4 }}>{status}</div>}
    </div>
  )
}

function SummarizeInfo({ empresaId, apiCall, onGoToUIs }) {
  const [absPath, setAbsPath] = useState(null)

  useEffect(() => {
    if (!empresaId || !apiCall) return
    apiCall('GET', `/summarizer/${empresaId}`, null)
      .then(data => { if (data?.path) setAbsPath(data.path) })
      .catch(() => {})
  }, [empresaId, apiCall])

  const displayPath = absPath || `data/summaries/${empresaId || '<empresa_id>'}/`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5 }}>
        Acumula cada mensaje entrante en un archivo <code style={{ color: '#94a3b8' }}>.md</code> por contacto.
        No produce reply — es un efecto de lado.
      </div>
      <div style={S.fieldWrap}>
        <span style={S.label}>RUTA DE ARCHIVOS</span>
        <code style={{ fontSize: 11, color: '#7dd3fc', background: '#0f172a', padding: '5px 8px', borderRadius: 5, wordBreak: 'break-all', userSelect: 'all' }}>
          {displayPath}
        </code>
      </div>
      {empresaId && onGoToUIs && (
        <button
          onClick={onGoToUIs}
          style={{ fontSize: 12, color: '#818cf8', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}
        >
          Ver resúmenes acumulados →
        </button>
      )}
    </div>
  )
}

// ─── Formulario principal ──────────────────────────────────────────────────────

const TRIGGER_TYPES = new Set(['whatsapp_trigger', 'telegram_trigger', 'message_trigger'])

function ConfigForm({ node, schema, empresaId, flowId, connections, apiCall, onGoToUIs }) {
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
  const [replaying, setReplaying]   = useState(false)
  const [replayMsg, setReplayMsg]   = useState('')
  const [fbRefreshing, setFbRefreshing] = useState(false)
  const [fbRefreshMsg, setFbRefreshMsg] = useState('')
  const [syncDate, setSyncDate]     = useState(() => new Date().toISOString().slice(0, 10))
  const [syncing, setSyncing]       = useState(false)
  const [syncMsg, setSyncMsg]       = useState('')

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
      }, 3000)
      setTimeout(() => { clearInterval(poll); setFbRefreshMsg(''); setFbRefreshing(false) }, 130_000)
    } catch {
      setFbRefreshMsg('⚠ Error de red')
      setTimeout(() => { setFbRefreshMsg(''); setFbRefreshing(false) }, 4000)
    }
  }

  async function handleSyncAll() {
    setSyncing(true)
    setSyncMsg('')
    try {
      const result = await apiCall('POST', `/summarizer/${empresaId}/sync-all?from_date=${syncDate}`, {})
      setSyncMsg(`✓ ${result.contacts} contactos sincronizados`)
    } catch {
      setSyncMsg('Error al sincronizar')
    } finally {
      setSyncing(false)
      setTimeout(() => setSyncMsg(''), 5000)
    }
  }

  async function handleReplay() {
    if (!flowId) return
    setReplaying(true)
    setReplayMsg('')
    try {
      const result = await apiCall('POST', `/empresas/${empresaId}/flows/${flowId}/replay`, {})
      setReplayMsg(`✓ ${result.processed ?? 0} mensajes procesados`)
    } catch {
      setReplayMsg('Error al re-sincronizar')
    } finally {
      setReplaying(false)
      setTimeout(() => setReplayMsg(''), 5000)
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
    if (f.type === 'contact_filter')         return { ...f, _contacts: contacts, _suggested: suggested }
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
          <button
            onClick={handleReplay}
            disabled={replaying}
            style={{
              width: '100%', padding: '7px 12px',
              background: replaying ? '#0f172a' : 'transparent',
              border: '1px solid #4c1d95',
              borderRadius: 6, color: '#a78bfa', fontSize: 12, cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {replaying ? '⏳ Re-triggering...' : '↺ Re-trigger histórico'}
          </button>
          {replayMsg && (
            <div style={{ fontSize: 11, color: '#a78bfa', textAlign: 'center' }}>{replayMsg}</div>
          )}

          {nodeType === 'whatsapp_trigger' && (
            <>
              <div style={{ borderTop: '1px solid #1e293b', marginTop: 4, paddingTop: 8 }}>
                <span style={S.label}>SYNC HISTÓRICO SUMARIZADOR</span>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: '#64748b', flexShrink: 0 }}>Desde</span>
                  <input
                    type="date"
                    style={{ ...S.input, flex: 1, colorScheme: 'dark' }}
                    value={syncDate}
                    onChange={e => setSyncDate(e.target.value)}
                  />
                </div>
                <button
                  onClick={handleSyncAll}
                  disabled={syncing || !syncDate}
                  style={{
                    width: '100%', padding: '7px 12px',
                    background: syncing ? '#0f172a' : 'transparent',
                    border: '1px solid #155e75',
                    borderRadius: 6, color: '#22d3ee', fontSize: 12, cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  {syncing ? '⏳ Sincronizando...' : '⟳ Sync todos los contactos desde esta fecha'}
                </button>
                {syncMsg && (
                  <div style={{ fontSize: 11, color: syncMsg.startsWith('✓') ? '#4ade80' : '#f87171', textAlign: 'center', marginTop: 4 }}>
                    {syncMsg}
                  </div>
                )}
              </div>
            </>
          )}

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

// ─── Export ───────────────────────────────────────────────────────────────────

export default function NodeConfigPanel({ empresaId, flowId, connections, apiCall, onGoToUIs }) {
  const nodes             = useFlowStore(s => s.nodes)
  const typeMap           = useFlowStore(s => s.typeMap)
  const selectedNodeId    = useFlowStore(s => s.selectedNodeId)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const selectedNode      = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null

  if (!selectedNode) return null

  const schema = typeMap[selectedNode.data.nodeType]?.schema || []

  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) setSelectedNodeId(null) }}
      style={{
        position: 'absolute', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.35)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
        pointerEvents: 'all',
      }}
    >
      <div style={{
        width: 420,
        height: '100%',
        background: '#0f172a',
        borderLeft: '1px solid #1e293b',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '-8px 0 32px rgba(0,0,0,0.5)',
        overflowY: 'auto',
        padding: 14,
      }}>
        <ConfigForm
          node={selectedNode}
          schema={schema}
          empresaId={empresaId}
          flowId={flowId}
          connections={connections}
          apiCall={apiCall}
          onGoToUIs={onGoToUIs}
        />
      </div>
    </div>
  )
}
