/**
 * NodeConfigPanel — panel lateral derecho para configurar el nodo seleccionado.
 *
 * Schema-driven: cada tipo de nodo declara sus campos en NODE_SCHEMAS.
 * Soporta: string, textarea, select, float, bool, list (tags separados por coma).
 */
import { useFlowStore } from '../store/flowStore.js'

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

// ─── Schemas por tipo de nodo ──────────────────────────────────────────────────

const NODE_SCHEMAS = {
  message_trigger: [
    { key: 'connection_id',   label: 'ID de conexión (bot_id)',            type: 'string',   required: true },
    { key: 'contact_phone',   label: 'Teléfono del contacto',              type: 'string',   hint: 'Dejar vacío para todos' },
    { key: 'message_pattern', label: 'Patrón regex',                       type: 'string',   hint: 'Opcional. Ej: .*urgente.*' },
  ],
  router: [
    { key: 'prompt',   label: 'Prompt del clasificador', type: 'textarea', rows: 7 },
    { key: 'routes',   label: 'Rutas válidas',           type: 'list',     hint: 'Separadas por coma — ej: noticias,oficio,auspiciante' },
    { key: 'fallback', label: 'Ruta por defecto',        type: 'string',   hint: 'Si el LLM responde algo inválido' },
    { key: 'model',    label: 'Modelo',                  type: 'string',   default: 'llama-3.3-70b-versatile' },
  ],
  llm: [
    { key: 'prompt',        label: 'System prompt',           type: 'textarea', rows: 8 },
    { key: 'model',         label: 'Modelo',                  type: 'string',   default: 'llama-3.3-70b-versatile' },
    { key: 'temperature',   label: 'Temperatura',             type: 'float',    default: 0.3 },
    { key: 'output',        label: 'Destino de la salida',    type: 'select',   options: ['reply', 'context', 'query'] },
    { key: 'json_output',   label: 'Respuesta JSON',          type: 'bool',     default: false },
    { key: 'json_reply_key',label: 'Clave JSON del reply',    type: 'string',   default: 'reply', hint: 'Solo si Respuesta JSON está activa' },
  ],
  send_message: [
    { key: 'to',      label: 'Destinatario',  type: 'string',   hint: 'Vacío = usuario de la conversación. Soporta {{placeholders}}' },
    { key: 'message', label: 'Mensaje',       type: 'textarea', rows: 5, hint: 'Soporta {{placeholders}} como {{worker_nombre}}' },
    { key: 'channel', label: 'Canal',         type: 'select',   options: ['auto', 'telegram', 'whatsapp'] },
  ],
  vector_search: [
    { key: 'collection',   label: 'Colección',              type: 'string', required: true, hint: 'ej: luganense_oficios, luganense_auspiciantes' },
    { key: 'query_field',  label: 'Fuente del query',       type: 'select', options: ['message', 'query', 'context'] },
    { key: 'output_field', label: 'Destino del resultado',  type: 'select', options: ['context', 'query'] },
    { key: 'top_k',        label: 'Cantidad de resultados', type: 'float',  default: 3 },
  ],
  fetch: [
    { key: 'source',        label: 'Fuente',                       type: 'select', options: ['facebook', 'fb_image', 'http'] },
    { key: 'fb_page_id',    label: 'Página de Facebook (slug)',    type: 'string', hint: 'ej: luganense, cnn, tuportal', showIf: c => c.source !== 'http' && c.source !== 'fb_image' },
    { key: 'fb_numeric_id', label: 'ID numérico FB (opcional)',    type: 'string', hint: 'Habilita búsqueda directa. Ej: 100070998865103', showIf: c => c.source !== 'http' && c.source !== 'fb_image' },
    { key: 'url',           label: 'URL',                          type: 'string', hint: 'https://...', showIf: c => c.source === 'http' },
    { key: 'extract',       label: 'Extraer',                      type: 'select', options: ['text', 'json', 'html'], showIf: c => c.source === 'http' },
  ],
  // summarize: sin config — se renderiza aparte con SummarizeInfo
}

// ─── Componentes de campo ──────────────────────────────────────────────────────

function Field({ field, config, onChange }) {
  const { key, label, type, hint, rows = 4, options = [], required } = field
  const value = config[key] ?? field.default ?? (type === 'bool' ? false : type === 'list' ? [] : '')

  function set(val) { onChange({ ...config, [key]: val }) }

  const labelEl = (
    <label style={S.label}>
      {label.toUpperCase()}{required && <span style={{ color: '#ef4444' }}> *</span>}
    </label>
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
        {options.map(o => <option key={o} value={o}>{o}</option>)}
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
    // Almacenamos como array, mostramos como string CSV editable
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

  // default: string
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

// Info especial para el nodo Sumarizador
function SummarizeInfo({ empresaId }) {
  const path = `data/summaries/${empresaId || '<empresa_id>'}/`
  const url  = `http://localhost:8000/api/summarizer/${empresaId || ''}`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5 }}>
        Acumula cada mensaje entrante en un archivo <code style={{ color: '#94a3b8' }}>.md</code> por contacto.
        No produce reply — es un efecto de lado.
      </div>
      <div style={S.fieldWrap}>
        <span style={S.label}>RUTA DE ARCHIVOS</span>
        <code style={{ fontSize: 11, color: '#7dd3fc', background: '#0f172a', padding: '5px 8px', borderRadius: 5, wordBreak: 'break-all' }}>
          {path}
        </code>
      </div>
      {empresaId && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 12, color: '#818cf8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          Ver resúmenes acumulados →
        </a>
      )}
    </div>
  )
}

// ─── Formulario principal ──────────────────────────────────────────────────────

function ConfigForm({ node, empresaId }) {
  const updateNodeConfig  = useFlowStore(s => s.updateNodeConfig)
  const deleteNode        = useFlowStore(s => s.deleteNode)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const { nodeType, config, label, color } = node.data

  const schema  = NODE_SCHEMAS[nodeType]
  const isFixed = nodeType === 'start' || nodeType === 'end'

  function handleChange(newConfig) { updateNodeConfig(node.id, newConfig) }
  function handleDelete() { if (!isFixed) { deleteNode(node.id) } }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', flex: 1 }}>{label}</span>
        <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{nodeType}</span>
        <button
          onClick={() => setSelectedNodeId(null)}
          style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 2 }}
          title="Cerrar"
        >×</button>
      </div>

      <div style={{ borderTop: '1px solid #1e293b', paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 12, flex: 1, overflowY: 'auto' }}>

        {/* Nodo sumarizador — info especial */}
        {nodeType === 'summarize' && (
          <SummarizeInfo empresaId={empresaId} />
        )}

        {/* Nodos con schema */}
        {schema && schema
          .filter(field => !field.showIf || field.showIf(config))
          .map(field => (
            <Field key={field.key} field={field} config={config} onChange={handleChange} />
          ))
        }

        {/* Nodos sin config conocida */}
        {!schema && nodeType !== 'summarize' && (
          <div style={{ fontSize: 12, color: '#475569' }}>
            Este nodo no tiene configuración adicional.
          </div>
        )}
      </div>

      {!isFixed && (
        <div style={{ marginTop: 'auto', paddingTop: 8 }}>
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

export default function NodeConfigPanel({ empresaId }) {
  const nodes          = useFlowStore(s => s.nodes)
  const selectedNodeId = useFlowStore(s => s.selectedNodeId)
  const selectedNode   = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null

  if (!selectedNode) {
    return (
      <div style={{
        width: 260,
        background: '#0f172a',
        borderLeft: '1px solid #1e293b',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 12, color: '#334155', textAlign: 'center', padding: 16 }}>
          Doble clic en un nodo para configurarlo
        </div>
      </div>
    )
  }

  return (
    <div style={{
      width: 260,
      background: '#0f172a',
      borderLeft: '1px solid #1e293b',
      padding: 14,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
    }}>
      <ConfigForm node={selectedNode} empresaId={empresaId} />
    </div>
  )
}
